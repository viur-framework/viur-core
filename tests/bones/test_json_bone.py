from abstract import ViURTestCase


class TestJsonBoneInit(ViURTestCase):

    def test_default_init(self):
        from viur.core.bones.json import JsonBone
        bone = JsonBone()
        self.assertEqual({}, bone.schema)

    def test_multiple_raises(self):
        from viur.core.bones.json import JsonBone
        with self.assertRaises(AssertionError):
            JsonBone(multiple=True)

    def test_indexed_raises(self):
        from viur.core.bones.json import JsonBone
        with self.assertRaises(AssertionError):
            JsonBone(indexed=True)

    def test_invalid_schema_raises(self):
        import jsonschema
        from viur.core.bones.json import JsonBone
        with self.assertRaises(jsonschema.SchemaError):
            JsonBone(schema={"type": "invalid_type"})


class TestJsonBoneSingleValueFromClient(ViURTestCase):

    def _from_client(self, bone, value):
        return bone.singleValueFromClient(value, {}, "data", {})

    def setUp(self):
        super().setUp()
        from viur.core.bones.json import JsonBone
        self.bone = JsonBone()

    def test_dict_passthrough(self):
        val, err = self._from_client(self.bone, {"key": "value"})
        self.assertIsNone(err)
        self.assertEqual({"key": "value"}, val)

    def test_list_passthrough(self):
        val, err = self._from_client(self.bone, [1, 2, 3])
        self.assertIsNone(err)
        self.assertEqual([1, 2, 3], val)

    def test_json_string_parsed(self):
        val, err = self._from_client(self.bone, '{"a": 1}')
        self.assertIsNone(err)
        self.assertEqual({"a": 1}, val)

    def test_python_dict_string_parsed(self):
        # ast.literal_eval fallback
        val, err = self._from_client(self.bone, "{'a': 1}")
        self.assertIsNone(err)
        self.assertEqual({"a": 1}, val)

    def test_invalid_json_returns_error(self):
        val, err = self._from_client(self.bone, "{invalid json}")
        self.assertIsNotNone(err)

    def test_empty_value_passthrough(self):
        # empty/falsy value → passes through to super()
        val, err = self._from_client(self.bone, None)
        self.assertIsNone(err)


class TestJsonBoneWithSchema(ViURTestCase):

    def _from_client(self, bone, value):
        return bone.singleValueFromClient(value, {}, "data", {})

    def setUp(self):
        super().setUp()
        from viur.core.bones.json import JsonBone
        self.bone = JsonBone(schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        })

    def test_valid_data_accepted(self):
        val, err = self._from_client(self.bone, {"name": "Alice", "age": 30})
        self.assertIsNone(err)

    def test_missing_required_field_rejected(self):
        val, err = self._from_client(self.bone, {"age": 30})
        self.assertIsNotNone(err)

    def test_wrong_type_rejected(self):
        val, err = self._from_client(self.bone, {"name": 123})
        self.assertIsNotNone(err)
