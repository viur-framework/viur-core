"""The JSON renderer answers every action with the response envelope (version 2)."""
import json
from unittest import mock

from abstract import ViURTestCase

ENVELOPE_KEYS = [
    "version", "action", "status", "step", "step_status", "steps", "follow",
    "datatype", "module", "structure", "data", "errors",
]


class FakeSkel:
    """Anything with dump() and structure() renders as an entity."""

    def __init__(self, values, errors=()):
        self.values = values
        self.errors = list(errors)

    def dump(self):
        return dict(self.values)

    def structure(self):
        return {"name": {"type": "str", "descr": "Name"}}


class FakeSkelList(list):

    def getCursor(self):
        return "c1"

    def get_orders(self):
        from viur.core import db
        return [("name", db.SortOrder.Descending)]


class EnvelopeTestCase(ViURTestCase):

    def setUp(self):
        super().setUp()
        from viur.core import Module, current, exposed
        from viur.core.render.json import default

        self.headers = {}
        current.request.set(mock.Mock(response=mock.Mock(headers=self.headers)))

        class Article(Module):
            @exposed
            def view(self):
                pass

        self.render = default(parent=Article("article", "/json/article"))

    def envelope(self, output):
        self.assertEqual("application/json", self.headers["Content-Type"])
        return json.loads(output)


class TestEntityEnvelope(EnvelopeTestCase):

    def test_carries_exactly_the_twelve_fields(self):
        result = self.envelope(self.render.view(FakeSkel({"name": "a"})))
        self.assertEqual(ENVELOPE_KEYS, list(result))

    def test_a_view_is_a_successful_entity(self):
        result = self.envelope(self.render.view(FakeSkel({"name": "a"})))
        self.assertEqual(2, result["version"])
        self.assertEqual(("view", "success", "entity", "article"),
                         (result["action"], result["status"], result["datatype"], result["module"]))
        self.assertEqual({"name": "a"}, result["data"])
        self.assertEqual({"name": {"type": "str", "descr": "Name"}}, result["structure"])
        self.assertEqual([], result["errors"])

    def test_an_empty_form_is_init(self):
        self.assertEqual("init", self.envelope(self.render.edit(FakeSkel({})))["status"])

    def test_a_form_with_errors_is_rejected_and_lists_them(self):
        from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
        error = ReadFromClientError(ReadFromClientErrorSeverity.Invalid, "Too short", ["name"], ["name"])

        result = self.envelope(self.render.add(FakeSkel({"name": "a"}, errors=[error])))

        self.assertEqual("rejected", result["status"])
        self.assertEqual("add", result["action"])
        self.assertEqual([{"error": "INVALID", "errorMessage": "Too short", "fieldPath": ["name"],
                           "invalidatedFields": ["name"], "severity": error.severity.value}], result["errors"])

    def test_success_verbs_are_reported_without_the_suffix(self):
        for method, verb in (("addSuccess", "add"), ("editSuccess", "edit"), ("deleteSuccess", "delete")):
            with self.subTest(method=method):
                result = self.envelope(getattr(self.render, method)(FakeSkel({"name": "a"})))
                self.assertEqual((verb, "success"), (result["action"], result["status"]))

    def test_the_deleted_entry_is_returned(self):
        self.assertEqual({"name": "a"}, self.envelope(self.render.deleteSuccess(FakeSkel({"name": "a"})))["data"])

    def test_explicit_workflow_values_win(self):
        from viur.core.actions import Status, Step
        result = self.envelope(self.render.edit(
            FakeSkel({}), status=Status.CONTINUE, step="otp", step_status=Status.SUCCESS,
            steps={"otp": Step(icon="key", icon_library="bootstrap", label="OTP")}, follow="/json/user/otp",
        ))
        self.assertEqual(("continue", "otp", "success", "/json/user/otp"),
                         (result["status"], result["step"], result["step_status"], result["follow"]))
        self.assertEqual({"otp": {"icon": "key", "icon_library": "bootstrap", "label": "OTP", "url": None}},
                         result["steps"])

    def test_next_url_becomes_follow(self):
        self.assertEqual("/next", self.envelope(self.render.render("structure.view", FakeSkel({}),
                                                                   next_url="/next"))["follow"])

    def test_a_payload_without_a_skeleton_is_data_without_structure(self):
        result = self.envelope(self.render.view({"url": "/upload"}))
        self.assertEqual(("entity", None, {"url": "/upload"}), (result["datatype"], result["structure"], result["data"]))

    def test_the_action_label_overrides_the_verb(self):
        from viur.core import current
        token = current.action.set("feedback")
        self.addCleanup(current.action.reset, token)
        self.assertEqual("feedback", self.envelope(self.render.edit(FakeSkel({})))["action"])


class TestListEnvelope(EnvelopeTestCase):

    def test_a_list_carries_meta_and_no_structure(self):
        result = self.envelope(self.render.list(FakeSkelList([FakeSkel({"name": "a"}), FakeSkel({"name": "b"})])))
        self.assertEqual(ENVELOPE_KEYS + ["meta"], list(result))
        self.assertEqual(("list", "success", "list", None),
                         (result["action"], result["status"], result["datatype"], result["structure"]))
        self.assertEqual([{"name": "a"}, {"name": "b"}], result["data"])
        self.assertEqual({"cursor": "c1", "orders": [{"field": "name", "dir": "desc"}]}, result["meta"])

    def test_an_empty_list_has_no_cursor(self):
        result = self.envelope(self.render.list(FakeSkelList()))
        self.assertEqual({"cursor": None, "orders": []}, result["meta"])
