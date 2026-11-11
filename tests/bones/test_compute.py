import threading

from abstract import ViURTestCase


class FakeSkel:
    """A stand-in for a SkeletonInstance.

    The computation guard identifies a skeleton by its ``accessedValues``, so that is
    all a stand-in needs. Two instances are two skeletons, as far as the guard is
    concerned.
    """

    def __init__(self):
        self.accessedValues = {}


class TestComputeGuard(ViURTestCase):
    """The recursion guard around a running ``compute``.

    It has to block exactly one thing -- the same bone reaching itself again on the
    same skeleton in the same thread -- and nothing else. It used to be a flag on the
    bone, which is shared by every skeleton of its class and by every thread, so it
    also blocked unrelated computations; those silently received the stored value
    instead of a computed one.
    """

    def _bone(self):
        from viur.core.bones import BaseBone
        return BaseBone()

    def test_mark_is_released_after_the_block(self):
        bone, skel = self._bone(), FakeSkel()

        self.assertFalse(bone.is_computing(skel, "value"))
        with bone.computing(skel, "value"):
            self.assertTrue(bone.is_computing(skel, "value"))
        self.assertFalse(bone.is_computing(skel, "value"))

    def test_mark_is_released_when_the_block_raises(self):
        bone, skel = self._bone(), FakeSkel()

        with self.assertRaises(ValueError):
            with bone.computing(skel, "value"):
                raise ValueError("compute function failed")

        # The previous flag stayed set here and disabled the bone for the rest of
        # the process.
        self.assertFalse(bone.is_computing(skel, "value"))

    def test_other_skeleton_is_not_blocked(self):
        bone, one, other = self._bone(), FakeSkel(), FakeSkel()

        with bone.computing(one, "value"):
            self.assertTrue(bone.is_computing(one, "value"))
            # A computation that reads the same bone of a *child* entity -- a total
            # summing up the totals below it, for instance -- must get through.
            self.assertFalse(bone.is_computing(other, "value"))

    def test_other_bone_is_not_blocked(self):
        bone, skel = self._bone(), FakeSkel()

        with bone.computing(skel, "value"):
            self.assertFalse(bone.is_computing(skel, "other_value"))

    def test_other_thread_is_not_blocked(self):
        """The regression: a concurrent request must not be refused a computation."""
        bone, skel = self._bone(), FakeSkel()
        entered = threading.Event()
        seen = {}

        def reader():
            entered.wait(timeout=5)
            # Deliberately the same bone *and* the same skeleton: even then the other
            # thread's computation says nothing about this one.
            seen["blocked"] = bone.is_computing(skel, "value")

        thread = threading.Thread(target=reader)
        thread.start()
        with bone.computing(skel, "value"):
            entered.set()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive(), "the reader thread did not finish")
        self.assertFalse(seen["blocked"])

    def test_marks_of_several_threads_do_not_leak(self):
        bone = self._bone()
        skels = [FakeSkel() for _ in range(4)]
        done = threading.Barrier(len(skels) + 1, timeout=5)
        leaked = []

        def worker(own):
            with bone.computing(own, "value"):
                for other in skels:
                    if other is not own and bone.is_computing(other, "value"):
                        leaked.append(other)
            done.wait()

        for skel in skels:
            threading.Thread(target=worker, args=(skel,)).start()
        done.wait()

        self.assertEqual([], leaked)
        for skel in skels:
            self.assertFalse(bone.is_computing(skel, "value"))


class TestConcurrentCompute(ViURTestCase):
    """A computation must not be refused because another thread is running one.

    This is the failure core#1792 describes: the guard lived on the bone, and a bone
    is shared by every skeleton of its class and by every thread. A request that read
    a computed bone while another request computed it got the stored value -- for a
    purely computed bone, ``None`` -- with no error and no log entry.
    """

    def _skel_class(self, compute_fn):
        from viur.core.bones import NumericBone
        from viur.core.bones.base import Compute, ComputeInterval, ComputeMethod
        from viur.core.skeleton import RelSkel

        class DemoSkel(RelSkel):
            value = NumericBone(
                precision=0,
                compute=Compute(compute_fn, ComputeInterval(ComputeMethod.Always)),
            )

        return DemoSkel

    def test_second_thread_gets_a_computed_value(self):
        gate = threading.Lock()
        claimed = []
        started = threading.Event()
        release = threading.Event()

        def compute_fn(skel):
            with gate:
                is_first = not claimed
                claimed.append(1)
            if is_first:
                # Hold the computation open until the other thread has read the bone.
                started.set()
                release.wait(timeout=5)
            return 7

        skel_class = self._skel_class(compute_fn)
        values = {}

        def hold():
            values["holder"] = skel_class()["value"]

        thread = threading.Thread(target=hold)
        thread.start()
        try:
            self.assertTrue(started.wait(timeout=5), "the holding computation never started")
            values["reader"] = skel_class()["value"]
        finally:
            release.set()
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive(), "the holding thread did not finish")
        self.assertEqual(7, values["reader"], "the concurrent read did not compute")
        self.assertEqual(7, values["holder"])

    def test_raw_value_unserialization_runs_without_the_mark(self):
        """The raw path has to be able to re-enter the bone.

        `_compute` releases the mark before it unserializes the raw value, and a bone
        whose `singleValueUnserialize` reaches its own bone again depends on that.
        `Compute.raw` defaults to True, so this is the path most computed bones take.
        """
        from viur.core.bones import NumericBone
        from viur.core.bones.base import Compute, ComputeInterval, ComputeMethod
        from viur.core.skeleton import RelSkel

        captured = {}
        seen = {}

        def compute_fn(skel):
            captured["skel"] = skel
            return 5

        class RecordingBone(NumericBone):
            def singleValueUnserialize(inner_self, val):
                seen["marked"] = inner_self.is_computing(captured["skel"], "value")
                return super().singleValueUnserialize(val)

        class DemoSkel(RelSkel):
            value = RecordingBone(
                precision=0,
                compute=Compute(compute_fn, ComputeInterval(ComputeMethod.Always)),
            )

        self.assertEqual(5, DemoSkel()["value"])
        self.assertIs(False, seen.get("marked"), "the mark was still held while unserializing the raw value")
