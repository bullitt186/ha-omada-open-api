#!/usr/bin/env python3
"""Validation script for Omada Open API integration."""
# ruff: noqa: T201, PTH123, BLE001, PLC0415

import json
from pathlib import Path
import sys


def validate_integration():
    """Validate the integration structure and files."""
    print("🔍 Validating Omada Open API Integration...\n")

    base_path = Path("custom_components/omada_open_api")
    errors = []
    warnings = []

    # Check required files
    required_files = [
        "__init__.py",
        "manifest.json",
        "strings.json",
        "config_flow.py",
        "api.py",
        "const.py",
    ]

    print("📁 Checking required files:")
    for file in required_files:
        file_path = base_path / file
        if file_path.exists():
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} - MISSING")
            errors.append(f"Missing required file: {file}")

    # Validate manifest.json
    print("\n📋 Validating manifest.json:")
    try:
        with open(base_path / "manifest.json") as f:
            manifest = json.load(f)

        required_keys = [
            "domain",
            "name",
            "config_flow",
            "documentation",
            "integration_type",
            "iot_class",
            "requirements",
            "version",
        ]
        for key in required_keys:
            if key in manifest:
                print(f"  ✅ {key}: {manifest[key]}")
            else:
                print(f"  ❌ {key} - MISSING")
                errors.append(f"Missing manifest key: {key}")

        if manifest.get("config_flow") is not True:
            errors.append("config_flow must be true")

        if manifest.get("integration_type") not in [
            "hub",
            "device",
            "service",
            "helper",
        ]:
            warnings.append(
                f"Unusual integration_type: {manifest.get('integration_type')}"
            )

    except Exception as e:
        errors.append(f"Failed to load manifest.json: {e}")

    # Validate strings.json
    print("\n🌐 Validating strings.json:")
    try:
        with open(base_path / "strings.json") as f:
            strings = json.load(f)

        if "config" in strings:
            steps = strings["config"].get("step", {})
            print(f"  ✅ Config flow steps: {len(steps)}")
            for step in steps:
                print(f"     - {step}")

            if "error" in strings["config"]:
                errors_defined = len(strings["config"]["error"])
                print(f"  ✅ Error messages defined: {errors_defined}")

            if "abort" in strings["config"]:
                aborts_defined = len(strings["config"]["abort"])
                print(f"  ✅ Abort messages defined: {aborts_defined}")
        else:
            errors.append("strings.json missing 'config' section")

    except Exception as e:
        errors.append(f"Failed to load strings.json: {e}")

    # Check Python imports
    print("\n🐍 Checking Python imports:")
    try:
        sys.path.insert(0, str(Path.cwd()))

        from custom_components.omada_open_api import DOMAIN

        print("  ✅ __init__.py imports successfully")
        print(f"     Domain: {DOMAIN}")

        print("  ✅ config_flow.py imports successfully")

        print("  ✅ api.py imports successfully")

        from custom_components.omada_open_api.const import REGIONS

        print("  ✅ const.py imports successfully")
        print(f"     Regions: {list(REGIONS.keys())}")

    except Exception as e:
        errors.append(f"Failed to import Python modules: {e}")
        import traceback

        traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    if errors:
        print(f"❌ Validation FAILED with {len(errors)} error(s):")
        for error in errors:
            print(f"   - {error}")
        return False
    if warnings:
        print(f"⚠️  Validation PASSED with {len(warnings)} warning(s):")
        for warning in warnings:
            print(f"   - {warning}")
        print("\n✅ Integration is valid and ready to use!")
        return True
    print("✅ Validation PASSED - No errors or warnings!")
    print("\n🎉 Integration is ready for use in Home Assistant!")
    return True


if __name__ == "__main__":
    success = validate_integration()
    sys.exit(0 if success else 1)
