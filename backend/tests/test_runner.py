"""
Comprehensive test runner with reporting and validation.
"""
import os
import subprocess
import sys
import time
from pathlib import Path



def run_all_tests():
    """Run all tests with comprehensive reporting."""
    print("=" * 80)
    print("FASTAPI BOOK READING BACKEND - COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    
    # Change to backend directory
    backend_dir = Path(__file__).parent.parent
    os.chdir(backend_dir)
    
    # Test categories
    test_categories = [
        ("Unit Tests", "test_*.py -m 'not integration and not performance and not security'"),
        ("Integration Tests", "test_integration.py"),
        ("Security Tests", "test_security.py"),
        ("Performance Tests", "test_performance.py"),
        ("Edge Cases", "test_edge_cases.py"),
        ("Services Tests", "test_services.py"),
        ("Upload Tests", "test_upload.py"),
        ("Middleware Tests", "test_middleware.py"),
    ]
    
    total_start_time = time.time()
    results = {}
    
    for category, test_pattern in test_categories:
        print(f"\n{'=' * 60}")
        print(f"Running {category}")
        print(f"{'=' * 60}")
        
        start_time = time.time()
        
        # Run pytest with specific pattern
        cmd = [
            "python", "-m", "pytest",
            "-v",
            "--tb=short",
            "--durations=10",
            "--maxfail=5"
        ]
        
        if "not" in test_pattern:
            cmd.extend(["-m", test_pattern.split("-m ")[1]])
        else:
            cmd.append(test_pattern)
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            duration = time.time() - start_time
            
            results[category] = {
                "returncode": result.returncode,
                "duration": duration,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
            if result.returncode == 0:
                print(f"✅ {category} PASSED ({duration:.2f}s)")
            else:
                print(f"❌ {category} FAILED ({duration:.2f}s)")
                print(f"Error output: {result.stderr[:500]}...")
                
        except subprocess.TimeoutExpired:
            print(f"⏱️  {category} TIMED OUT (>300s)")
            results[category] = {"returncode": -1, "duration": 300, "timeout": True}
        except Exception as e:
            print(f"💥 {category} ERROR: {e}")
            results[category] = {"returncode": -2, "duration": 0, "error": str(e)}
    
    # Generate summary report
    total_duration = time.time() - total_start_time
    print(f"\n{'=' * 80}")
    print("TEST EXECUTION SUMMARY")
    print(f"{'=' * 80}")
    print(f"Total execution time: {total_duration:.2f} seconds")
    print()
    
    passed = 0
    failed = 0
    
    for category, result in results.items():
        status = "PASSED" if result["returncode"] == 0 else "FAILED"
        duration = result["duration"]
        symbol = "✅" if result["returncode"] == 0 else "❌"
        
        print(f"{symbol} {category:<25} {status:<8} ({duration:>6.2f}s)")
        
        if result["returncode"] == 0:
            passed += 1
        else:
            failed += 1
    
    print(f"\n📊 Overall Results: {passed} passed, {failed} failed")
    
    # Coverage report
    print(f"\n{'=' * 60}")
    print("GENERATING COVERAGE REPORT")
    print(f"{'=' * 60}")
    
    try:
        coverage_cmd = [
            "python", "-m", "pytest",
            "--cov=app",
            "--cov-report=term-missing",
            "--cov-report=html",
            "--cov-fail-under=80",
            "-q"
        ]
        
        coverage_result = subprocess.run(coverage_cmd, capture_output=True, text=True, timeout=120)
        
        if coverage_result.returncode == 0:
            print("✅ Coverage report generated successfully")
            print("📁 HTML report available in htmlcov/index.html")
        else:
            print("⚠️  Coverage report had issues:")
            print(coverage_result.stdout[-500:])
            
    except Exception as e:
        print(f"❌ Coverage report failed: {e}")
    
    # Final recommendations
    print(f"\n{'=' * 80}")
    print("RECOMMENDATIONS")
    print(f"{'=' * 80}")
    
    if failed == 0:
        print("🎉 ALL TESTS PASSED! Your backend is ready for production.")
        print("✨ Excellent code quality and test coverage.")
    elif failed <= 2:
        print("⚠️  Most tests passed, but some issues need attention.")
        print("🔧 Review failed tests and fix any critical issues.")
    else:
        print("🚨 Multiple test failures detected.")
        print("🛠️  Significant issues need to be resolved before deployment.")
    
    print("\n📋 Next Steps:")
    print("1. Review any failed tests and fix underlying issues")
    print("2. Check coverage report for untested code")
    print("3. Run performance tests under load")
    print("4. Verify security test results")
    print("5. Update documentation if needed")
    
    return failed == 0


def run_specific_test_suite(suite_name):
    """Run a specific test suite."""
    suites = {
        "unit": "test_*.py -m 'not integration and not performance and not security'",
        "integration": "test_integration.py",
        "security": "test_security.py", 
        "performance": "test_performance.py",
        "edge": "test_edge_cases.py",
        "services": "test_services.py",
        "upload": "test_upload.py",
        "middleware": "test_middleware.py"
    }
    
    if suite_name not in suites:
        print(f"❌ Unknown test suite: {suite_name}")
        print(f"Available suites: {', '.join(suites.keys())}")
        return False
    
    print(f"Running {suite_name} test suite...")
    
    cmd = ["python", "-m", "pytest", "-v", "--tb=short"]
    
    if "not" in suites[suite_name]:
        cmd.extend(["-m", suites[suite_name].split("-m ")[1]])
    else:
        cmd.append(suites[suite_name])
    
    result = subprocess.run(cmd)
    return result.returncode == 0


def validate_test_environment():
    """Validate test environment setup."""
    print("🔍 Validating test environment...")
    
    # Check if we're in the right directory
    if not Path("app").exists():
        print("❌ Not in backend directory or app module not found")
        return False
    
    # Check if test files exist
    test_files = [
        "tests/conftest.py",
        "tests/test_auth.py",
        "tests/test_users.py",
        "tests/test_books.py",
        "tests/test_integration.py",
        "tests/test_security.py",
        "tests/test_performance.py"
    ]
    
    missing_files = []
    for test_file in test_files:
        if not Path(test_file).exists():
            missing_files.append(test_file)
    
    if missing_files:
        print(f"❌ Missing test files: {', '.join(missing_files)}")
        return False
    
    # Check if pytest is available
    try:
        result = subprocess.run(["python", "-m", "pytest", "--version"], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ pytest not available")
            return False
    except Exception:
        print("❌ pytest not available")
        return False
    
    # Check database connection
    try:
        from app.core.database import get_db
        next(get_db())
        print("✅ Database connection successful")
    except Exception as e:
        print(f"⚠️  Database connection issue: {e}")
        print("Tests may fail if database is not properly configured")
    
    print("✅ Test environment validation passed")
    return True


def main():
    """Main test runner function."""
    if len(sys.argv) > 1:
        suite_name = sys.argv[1]
        if suite_name == "validate":
            success = validate_test_environment()
            sys.exit(0 if success else 1)
        else:
            success = run_specific_test_suite(suite_name)
            sys.exit(0 if success else 1)
    else:
        if not validate_test_environment():
            print("❌ Environment validation failed")
            sys.exit(1)
        
        success = run_all_tests()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 