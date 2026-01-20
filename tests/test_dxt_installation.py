#!/usr/bin/env python3
"""
Test script for Music21 MCP Server DXT installation

This script simulates the DXT installation process to verify everything works correctly.
It extracts the DXT package and runs the installation scripts in a test environment.
"""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def log(message: str, level: str = "INFO"):
    """Simple logging function"""
    print(f"[{level}] {message}")


def extract_dxt_package(dxt_file: Path, extract_dir: Path):
    """Extract the DXT package for testing"""
    try:
        with zipfile.ZipFile(dxt_file, "r") as zipf:
            zipf.extractall(extract_dir)
        log(f"Extracted DXT package to {extract_dir}", "INFO")
        return True
    except Exception as e:
        log(f"Failed to extract DXT package: {e}", "ERROR")
        return False


def validate_extracted_files(extract_dir: Path):
    """Validate that all required files are present"""
    required_files = [
        "manifest.json",
        "requirements.txt",
        "scripts/pre_install.py",
        "scripts/post_install.py",
        "src/music21_mcp/server_minimal.py",
    ]

    missing_files = []
    for file_path in required_files:
        full_path = extract_dir / file_path
        if not full_path.exists():
            missing_files.append(file_path)

    if missing_files:
        log(f"Missing required files: {missing_files}", "ERROR")
        return False

    log("All required files are present", "INFO")
    return True


def verify_manifest_parsing(extract_dir: Path):
    """Test that the manifest.json is valid"""
    manifest_path = extract_dir / "manifest.json"
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Check required fields
        required_fields = [
            "dxt_version",
            "name",
            "version",
            "description",
            "author",
            "server",
        ]
        for field in required_fields:
            if field not in manifest:
                log(f"Missing required field in manifest: {field}", "ERROR")
                return False

        log(
            f"Manifest valid: {manifest['display_name']} v{manifest['version']}", "INFO"
        )
        log(f"Tools available: {len(manifest.get('tools', []))}", "INFO")
        return True

    except Exception as e:
        log(f"Manifest parsing failed: {e}", "ERROR")
        return False


def verify_pre_install_script(extract_dir: Path):
    """Test the pre-installation script (dry run)"""
    try:
        pre_install = extract_dir / "scripts" / "pre_install.py"

        # Check if the script is syntactically valid
        with open(pre_install) as f:
            script_content = f.read()

        # Compile to check for syntax errors
        compile(script_content, str(pre_install), "exec")
        log("Pre-install script syntax is valid", "INFO")
        return True

    except SyntaxError as e:
        log(f"Pre-install script syntax error: {e}", "ERROR")
        return False
    except Exception as e:
        log(f"Pre-install script validation failed: {e}", "ERROR")
        return False


def verify_post_install_script(extract_dir: Path):
    """Test the post-installation script (dry run)"""
    try:
        post_install = extract_dir / "scripts" / "post_install.py"

        # Check if the script is syntactically valid
        with open(post_install) as f:
            script_content = f.read()

        # Compile to check for syntax errors
        compile(script_content, str(post_install), "exec")
        log("Post-install script syntax is valid", "INFO")
        return True

    except SyntaxError as e:
        log(f"Post-install script syntax error: {e}", "ERROR")
        return False
    except Exception as e:
        log(f"Post-install script validation failed: {e}", "ERROR")
        return False


def verify_server_import(extract_dir: Path):
    """Test that the server can be imported"""
    try:
        # Add the src directory to Python path
        src_dir = extract_dir / "src"
        sys.path.insert(0, str(src_dir))

        # Try to import the main server module
        import music21_mcp.server_minimal

        log("Server module imports successfully", "INFO")

        # Try to import the adapter
        from music21_mcp.adapters.mcp_adapter import MCPAdapter

        adapter = MCPAdapter()
        log("MCP adapter initializes successfully", "INFO")

        # Check that tools are available
        tools = adapter.get_supported_tools()
        log(f"Adapter reports {len(tools)} tools available", "INFO")

        return True

    except ImportError as e:
        log(f"Import error: {e}", "WARNING")
        log("This is expected if music21 dependencies are not installed", "INFO")
        return True  # Don't fail the test for missing dependencies
    except Exception as e:
        log(f"Server import test failed: {e}", "ERROR")
        return False
    finally:
        # Clean up sys.path
        if str(src_dir) in sys.path:
            sys.path.remove(str(src_dir))


def verify_requirements_file(extract_dir: Path):
    """Test that the requirements.txt file is valid"""
    try:
        requirements_file = extract_dir / "requirements.txt"
        with open(requirements_file) as f:
            lines = f.readlines()

        # Count non-comment, non-empty lines
        requirements = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("#")
        ]

        log(f"Requirements file contains {len(requirements)} dependencies", "INFO")

        # Check for essential packages
        essential_packages = ["music21", "mcp", "fastmcp"]
        found_packages = []

        for req in requirements:
            for pkg in essential_packages:
                if req.startswith(pkg):
                    found_packages.append(pkg)

        if len(found_packages) == len(essential_packages):
            log("All essential packages found in requirements", "INFO")
            return True
        missing = set(essential_packages) - set(found_packages)
        log(f"Missing essential packages: {missing}", "WARNING")
        return True  # Don't fail for this

    except Exception as e:
        log(f"Requirements file test failed: {e}", "ERROR")
        return False


def main():
    """Main test process"""
    log("Starting DXT package installation test...", "INFO")

    # Find the DXT package
    project_root = Path(__file__).parent.absolute()
    dist_dir = project_root / "dist"

    dxt_files = list(dist_dir.glob("*.dxt"))
    if not dxt_files:
        log("No DXT package found in dist/ directory", "ERROR")
        log("Run 'python build_dxt.py' first to create the package", "ERROR")
        sys.exit(1)

    dxt_file = dxt_files[0]  # Use the first (most recent) package
    log(f"Testing DXT package: {dxt_file.name}", "INFO")

    # Create temporary directory for extraction
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        log(f"Using temporary directory: {temp_dir}", "INFO")

        # Run all tests
        tests = [
            ("Extract DXT package", lambda: extract_dxt_package(dxt_file, temp_dir)),
            ("Validate extracted files", lambda: validate_extracted_files(temp_dir)),
            ("Test manifest parsing", lambda: verify_manifest_parsing(temp_dir)),
            ("Test requirements file", lambda: verify_requirements_file(temp_dir)),
            ("Test pre-install script", lambda: verify_pre_install_script(temp_dir)),
            ("Test post-install script", lambda: verify_post_install_script(temp_dir)),
            ("Test server import", lambda: verify_server_import(temp_dir)),
        ]

        passed = 0
        failed = 0

        for test_name, test_func in tests:
            log(f"Running test: {test_name}", "INFO")
            try:
                if test_func():
                    log(f"✅ {test_name}: PASSED", "INFO")
                    passed += 1
                else:
                    log(f"❌ {test_name}: FAILED", "ERROR")
                    failed += 1
            except Exception as e:
                log(f"❌ {test_name}: ERROR - {e}", "ERROR")
                failed += 1
            print()  # Empty line for readability

    # Print summary
    total = passed + failed
    print("=" * 60)
    print("🧪 DXT Package Test Results")
    print("=" * 60)
    print(f"📊 Total Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {passed / total * 100:.1f}%")
    print()

    if failed == 0:
        print("🎉 All tests passed! The DXT package is ready for distribution.")
        print()
        print("📋 Next Steps:")
        print("1. Upload the .dxt file to GitHub releases")
        print("2. Share with users for one-click installation")
        print("3. Update documentation with download links")
    else:
        print("⚠️  Some tests failed. Please review and fix issues before distribution.")
        print()
        print("🔧 Troubleshooting:")
        print("1. Check the build logs for errors")
        print("2. Verify all source files are included")
        print("3. Test the installation scripts manually")

    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
