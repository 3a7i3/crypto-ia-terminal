# PowerShell script to run all tests with correct PYTHONPATH
$env:PYTHONPATH = "my_trading_system"
python -m unittest discover -s my_trading_system/tests
