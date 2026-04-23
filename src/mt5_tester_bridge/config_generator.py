"""MT5 Tester Config Generator.

Generates .set files and configuration for MT5 Strategy Tester.
Maps chain_gambler config to MT5 tester settings.
"""
import os
from typing import Optional


def generate_set_file(symbol: str, period: str = "2024.01.01-2024.12.31",
                      initial_deposit: float = 10000, leverage: int = 2000000000,
                      output_dir: str = ".", config_overrides: dict = None) -> str:
    """Generate a Strategy Tester .set file.

    The .set file configures the tester: symbol, timeframe, deposit, etc.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Parse period
    date_from = "2024.01.01"
    date_to = "2024.12.31"
    if "-" in period:
        parts = period.split("-", 1)
        date_from = parts[0].strip()
        date_to = parts[1].strip()

    overrides = config_overrides or {}

    # MT5 Strategy Tester configuration
    # These are written to the terminal configuration
    set_content = f"""\
; Chain Gambler Strategy Tester Configuration
; Generated automatically by bridge
; Symbol: {symbol}

;--- Tester Settings ---
TestSymbol={symbol}
TestPeriod=M5
TestModel=0                          ; 0=Every tick, 1=1 min OHLC, 2=Open prices only
TestFromDate={date_from}
TestToDate={date_to}
TestDeposit={initial_deposit}
TestLeverage=1:{leverage}
TestExecutionMode=0                   ; 0=Normal, 1=Delayed, 2=Custom

;--- Spread Settings ---
TestSpread=0                          ; 0=Current, >0=fixed spread in points
TestSpreadMultiplier=1.0              ; Spread multiplier for testing

;--- Optimization ---
TestOptimization=0                     ; 0=Disabled, 1=Slow, 2=Fast
TestCriterion=0                        ; 0=Balance, 1=Profit Factor, 2=Recovery

;--- EA Parameters ---
LotSize={overrides.get('lot_size', 0.01)}
MagicNumber={overrides.get('magic_number', 505)}
MaxSlippage={overrides.get('max_slippage', 10)}
SpreadLimit={overrides.get('spread_limit', 50)}
"""

    set_path = os.path.join(output_dir, f"tester_{symbol}.set")
    with open(set_path, "w", encoding="utf-8") as f:
        f.write(set_content)

    return set_path


def generate_terminal_ini(symbol: str, ea_name: str, output_dir: str,
                          period: str = "2024.01.01-2024.12.31",
                          deposit: float = 10000) -> str:
    """Generate terminal.ini configuration for headless tester execution.

    This configures MT5's terminal to run the Strategy Tester
    without GUI interaction.
    """
    date_from = "2024.01.01"
    date_to = "2024.12.31"
    if "-" in period:
        parts = period.split("-", 1)
        date_from = parts[0].strip()
        date_to = parts[1].strip()

    ini_content = f"""\
[Tester]
Expert={ea_name}
ExpertParameters=tests\\{ea_name}.set
Symbol={symbol}
Period=M5
Model=0
FromDate={date_from}
ToDate={date_to}
Deposit={deposit}
Leverage=1:2000000000
ExecutionMode=0
Optimization=0
"""

    ini_path = os.path.join(output_dir, "terminal.ini")
    with open(ini_path, "w", encoding="utf-8") as f:
        f.write(ini_content)

    return ini_path