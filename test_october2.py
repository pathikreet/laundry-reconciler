import pandas as pd

def process(file_path):
    print(f"Processing {file_path}")
    df = pd.read_csv(file_path)
    
    if not df.empty:
        col_0 = str(df.columns[0]).strip()
        if col_0.startswith('T') and col_0[1:].isdigit():
            first_row_data = df.columns.tolist()
            for i, val in enumerate(first_row_data):
                if str(val).startswith('Unnamed:'):
                    first_row_data[i] = None
            header_df = pd.DataFrame([first_row_data], columns=df.columns)
            df = pd.concat([header_df, df], ignore_index=True)
            
            expected_cols = ['Order Number', 'Customer Name', 'Amount', 'Payment Mode', 'Delivery Date', 'Runner Name', 'Notes']
            new_cols = expected_cols.copy()
            
            if len(df.columns) > len(expected_cols):
                for i in range(len(df.columns) - len(expected_cols)):
                    new_cols.append(f'Extra_{i}')
            elif len(df.columns) < len(expected_cols):
                for missing_col in expected_cols[len(df.columns):]:
                    df[missing_col] = None
                    new_cols.append(missing_col)
            df.columns = new_cols[:len(df.columns)]
    
    df = df.where(pd.notnull(df), None)
    raw_data = df.to_dict(orient='records')
    
    # now normalize!
    for i, row in enumerate(raw_data):
        try:
            amount = row.get('Amount')
            if amount is not None and str(amount).strip() != '':
                val_str = str(amount).replace(',', '').strip()
                float(eval(val_str))
        except Exception as e:
            print(f"Row {i} error on eval: amount='{amount}' -> {e}")
            break
            
    print("Done checking.", len(raw_data))

process('d:/Pathikreet/Workspace/Laundry-Reconciler/laundry-reconciler-docs/sample/Delivery_notes_October.csv')
