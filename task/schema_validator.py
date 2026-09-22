"""
Lightweight, robust JSON Schema validator for subagent output contracts.
Zero external dependencies.
Supports object properties, required keys, array items, primitives, enums,
union types, nullable fields, anyOf/oneOf/allOf, and numeric/string/array bounds.
"""

from typing import Any, Dict, List, Optional, Tuple, Union


def validate_schema(data: Any, schema: Optional[Dict[str, Any]], path: str = "") -> Tuple[bool, Optional[str]]:
    """
    Validate `data` against a JSON Schema definition `schema`.
    Returns (True, None) on success, or (False, error_message) on validation failure.
    """
    if not schema or not isinstance(schema, dict):
        return True, None

    # Try using jsonschema if installed
    try:
        import jsonschema
        try:
            jsonschema.validate(instance=data, schema=schema)
            return True, None
        except jsonschema.ValidationError as err:
            err_path = ".".join(str(p) for p in err.path) if err.path else "root"
            return False, f"Validation failed at '{err_path}': {err.message}"
    except ImportError:
        pass

    # Built-in lightweight validator
    return _validate_node(data, schema, path or "root")


def _validate_node(data: Any, schema: Dict[str, Any], path: str) -> Tuple[bool, Optional[str]]:
    if not isinstance(schema, dict):
        return True, None

    # 1. Nullable check (OpenAPI convention)
    if data is None and schema.get("nullable") is True:
        return True, None

    # 2. anyOf / oneOf / allOf composition
    if "anyOf" in schema:
        any_valid = False
        for sub in schema["anyOf"]:
            if isinstance(sub, dict) and _validate_node(data, sub, path)[0]:
                any_valid = True
                break
        if not any_valid:
            return False, f"Field '{path}' did not match any schema in 'anyOf'"

    if "oneOf" in schema:
        match_count = sum(1 for sub in schema["oneOf"] if isinstance(sub, dict) and _validate_node(data, sub, path)[0])
        if match_count != 1:
            return False, f"Field '{path}' matched {match_count} schemas in 'oneOf' (expected exactly 1)"

    if "allOf" in schema:
        for sub in schema["allOf"]:
            if isinstance(sub, dict):
                valid, err = _validate_node(data, sub, path)
                if not valid:
                    return False, err

    # 3. Enum check
    if "enum" in schema:
        allowed = schema["enum"]
        if data not in allowed:
            return False, f"Field '{path}' value {repr(data)} is not in allowed enum values {allowed}"

    # 4. Type validation (single string or list of union types)
    expected_type = schema.get("type")
    if expected_type:
        type_valid, type_err = _check_type(data, expected_type, path)
        if not type_valid:
            return False, type_err

    # 5. Numeric bounds validation
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            return False, f"Field '{path}' value {data} is less than minimum {schema['minimum']}"
        if "maximum" in schema and data > schema["maximum"]:
            return False, f"Field '{path}' value {data} is greater than maximum {schema['maximum']}"

    # 6. String length bounds validation
    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            return False, f"Field '{path}' length {len(data)} is less than minLength {schema['minLength']}"
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            return False, f"Field '{path}' length {len(data)} is greater than maxLength {schema['maxLength']}"

    # 7. Object validation
    if expected_type == "object" or (isinstance(data, dict) and "properties" in schema):
        if not isinstance(data, dict):
            return False, f"Field '{path}' expected object, got {type(data).__name__}"

        # Required fields check
        required_fields = schema.get("required", [])
        for req in required_fields:
            if req not in data:
                return False, f"Missing required property '{req}' at '{path}'"

        # Properties validation
        properties = schema.get("properties", {})
        for prop_name, prop_schema in properties.items():
            if prop_name in data:
                child_path = f"{path}.{prop_name}" if path != "root" else prop_name
                valid, err = _validate_node(data[prop_name], prop_schema, child_path)
                if not valid:
                    return False, err

    # 8. Array validation
    if expected_type == "array" or (isinstance(data, list) and "items" in schema):
        if not isinstance(data, list):
            return False, f"Field '{path}' expected array, got {type(data).__name__}"

        if "minItems" in schema and len(data) < schema["minItems"]:
            return False, f"Field '{path}' items count {len(data)} is less than minItems {schema['minItems']}"
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            return False, f"Field '{path}' items count {len(data)} is greater than maxItems {schema['maxItems']}"

        items_schema = schema.get("items")
        if items_schema and isinstance(items_schema, dict):
            for idx, item in enumerate(data):
                child_path = f"{path}[{idx}]"
                valid, err = _validate_node(item, items_schema, child_path)
                if not valid:
                    return False, err

    return True, None


def _check_type(data: Any, expected_type: Union[str, List[str]], path: str) -> Tuple[bool, Optional[str]]:
    """Validate data type against a single expected type string or list of union types."""
    if isinstance(expected_type, list):
        for t in expected_type:
            valid, _ = _check_single_type(data, str(t), path)
            if valid:
                return True, None
        return False, f"Field '{path}' expected one of types {expected_type}, got {type(data).__name__}"
    return _check_single_type(data, str(expected_type), path)


def _check_single_type(data: Any, expected_type: str, path: str = "") -> Tuple[bool, Optional[str]]:
    """Check data against a single type string."""
    if expected_type == "string":
        if not isinstance(data, str):
            return False, f"Field '{path}' expected string, got {type(data).__name__}"
    elif expected_type in ("number", "float"):
        if not isinstance(data, (int, float)) or isinstance(data, bool):
            return False, f"Field '{path}' expected number, got {type(data).__name__}"
    elif expected_type == "integer":
        if not isinstance(data, int) or isinstance(data, bool):
            return False, f"Field '{path}' expected integer, got {type(data).__name__}"
    elif expected_type == "boolean":
        if not isinstance(data, bool):
            return False, f"Field '{path}' expected boolean, got {type(data).__name__}"
    elif expected_type == "object":
        if not isinstance(data, dict):
            return False, f"Field '{path}' expected object, got {type(data).__name__}"
    elif expected_type == "array":
        if not isinstance(data, list):
            return False, f"Field '{path}' expected array, got {type(data).__name__}"
    elif expected_type == "null":
        if data is not None:
            return False, f"Field '{path}' expected null, got {type(data).__name__}"
    return True, None
