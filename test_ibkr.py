"""
Quick connection test for IB Gateway.
Copy backend/.env.example to backend/.env and set IBKR_HOST before running.
"""
import os
from dotenv import load_dotenv
load_dotenv('backend/.env')

from ib_insync import IB

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4002"))

ib = IB()
try:
    ib.connect(IBKR_HOST, IBKR_PORT, clientId=10, timeout=15)
    print("✅ Verbindung erfolgreich!")
    for av in ib.accountValues():
        if av.tag in ['NetLiquidation', 'TotalCashValue', 'BuyingPower']:
            print(f"  {av.tag}: {av.value} {av.currency}")
except Exception as e:
    print(f"❌ Fehler: {e}")
finally:
    ib.disconnect()
