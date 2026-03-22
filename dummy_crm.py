import pandas as pd
from datetime import datetime

# Create dummy CRM data
data = {
    'Order Number': ['ORD-001', 'ORD-002'],
    'Name': ['John Doe', 'Jane Smith'],
    'Amount': [100.0, 200.0],
    'Date': [datetime.today(), datetime.today()]
}
df = pd.DataFrame(data)
df.to_excel('dummy_crm.xlsx', index=False)
print("Created dummy_crm.xlsx")
