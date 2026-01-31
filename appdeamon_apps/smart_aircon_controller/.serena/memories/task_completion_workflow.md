# Task Completion Workflow

## When a coding task is completed:

### 1. Testing:
```bash
# Always run the full test suite
python3 run_tests.py

# Run with coverage if making significant changes
python3 run_tests.py --coverage
```

### 2. Code Quality:
- Ensure all type hints are present
- Check docstrings are updated
- Verify error handling is appropriate
- Follow the established class-based architecture

### 3. Integration Testing:
```bash
# Test specific scenarios
python3 run_comprehensive_scenario.py
python3 final_verification_test.py
```

### 4. Configuration Validation:
- Verify `apps.yaml` configuration is valid
- Check Home Assistant entity references
- Ensure zone configurations are correct

### 5. Documentation:
- Update README.md if public API changes
- Update inline documentation if algorithm changes
- No need to create new documentation files unless explicitly requested

### 6. AppDaemon Integration:
- Test with AppDaemon if possible
- Verify Home Assistant entity integration
- Check sensor and service creation