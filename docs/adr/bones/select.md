---
covers: [viur.core.bones.select.SelectBone, viur.core.bones.select.translation_key_prefix_bonename, viur.core.bones.select.translation_key_prefix_skeleton_bonename]
status: accepted
---
## Seam
`SelectBone` restricts a value to the keys of `values`. `values` accepts a
dict, a list/tuple (key == label), a **callable** returning either, or an
`enum.EnumMeta`. With an Enum the bone stores `value.value` but hands out Enum
members.

Labels become `i18n.translate` objects automatically. The translation key is
`f"{translation_key_prefix}{key}"`; ready-made prefix helpers are
`translation_key_prefix_bonename` and
`translation_key_prefix_skeleton_bonename`, or pass your own callable.

## Rules
- Use a callable for `values` when the options come from the datastore or
  config - it is re-evaluated on every access, so no restart is needed.
- With an Enum, the *values* are what is stored (and the member *names* become
  the labels). Renaming a member is safe, changing its value is a data
  migration.
- `structure()` reports the options as a dict. Projects that still need the
  old list-of-tuples format enable it through
  `"bone.select.structure.values.keytuple"` in `conf.compatibility`.
- `add_missing_translations=True` writes translation entries for the labels;
  keep it off in production for the same reasons as
  `conf.i18n.add_missing_translations`.

## Traps
- `values` is a property implemented in `__getattribute__`: every single access
  re-evaluates the callable and re-builds one `translate` object per option.
  `singleValueFromClient` iterates it, so a select with many options is
  measurably expensive per request. Cache it yourself if it hurts.
- The auto-generated translation hint dereferences `self.skel_cls.__name__`.
  Accessing `.values` on a bone that is not bound to a skeleton class raises
  AttributeError.
- `singleValueFromClient` compares `str(key) == value`, so `1` and `"1"` are
  the same option - and two keys that only differ in type collide.
- An empty submitted value yields `Empty`, not `Invalid`, so a non-required
  select silently ends up unset instead of reporting a wrong option.
- `singleValueSerialize` goes through `_atomic_dump`, so what is stored is the
  dump representation - relevant when overriding one of them.
- `structure()` resolves the labels with `str(v)`, i.e. into the language of
  the current request. The structure of a select bone is language dependent
  and must not be cached across languages.
- A stored value that is no longer a member of the Enum is handed back
  unchanged by `singleValueUnserialize` - no error, just a raw value where the
  application expects an Enum member.

## See also
[base](base.md), [selectcountry](selectcountry.md), [../i18n](../i18n.md)
