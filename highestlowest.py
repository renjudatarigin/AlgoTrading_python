import io
import datetime
import pandas as pd
from azure.storage.blob import BlobServiceClient

# ======================
# 🔧 CONFIGURATION
# ======================
AZURE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=storageaccountdatarig;AccountKey=mlqWv0MzjNhM40m0Z26BOH556vg7n2oOEqdNm3BkxjtzBRwFGmSnYBZ+wm0kxY2mYOGe4FFjgSa3+AStN8sb/Q==;EndpointSuffix=core.windows.net"
CONTAINER_NAME = "stockdata"

# ======================
# 📅 MANUAL DATE (FORMAT: YYYYMMDD)
# ======================
# Example: "20251111" for 11th Nov 2025
MANUAL_DATE = "20251111"   # 👈 Change this as needed
TODAY_FOLDER = f"{MANUAL_DATE}/"

# ======================
# 🎯 STOCK TOKEN LIST
# ======================
token_list = [
    {"exchangeType": 1, "tokens": ["11532"]}, {"exchangeType": 1, "tokens": ["10604"]},
    {"exchangeType": 1, "tokens": ["11536"]}, {"exchangeType": 1, "tokens": ["11630"]},
    {"exchangeType": 1, "tokens": ["11723"]}, {"exchangeType": 1, "tokens": ["10999"]},
    {"exchangeType": 1, "tokens": ["11483"]}, {"exchangeType": 1, "tokens": ["1232"]},
    {"exchangeType": 1, "tokens": ["1363"]}, {"exchangeType": 1, "tokens": ["1394"]},
    {"exchangeType": 1, "tokens": ["1660"]}, {"exchangeType": 1, "tokens": ["16669"]},
    {"exchangeType": 1, "tokens": ["157"]}, {"exchangeType": 1, "tokens": ["20374"]},
    {"exchangeType": 1, "tokens": ["1964"]}, {"exchangeType": 1, "tokens": ["1594"]},
    {"exchangeType": 1, "tokens": ["16675"]}, {"exchangeType": 1, "tokens": ["21808"]},
    {"exchangeType": 1, "tokens": ["2475"]}, {"exchangeType": 1, "tokens": ["1922"]},
    {"exchangeType": 1, "tokens": ["1333"]}, {"exchangeType": 1, "tokens": ["13538"]},
    {"exchangeType": 1, "tokens": ["3499"]}, {"exchangeType": 1, "tokens": ["15083"]},
    {"exchangeType": 1, "tokens": ["467"]}, {"exchangeType": 1, "tokens": ["17963"]},
    {"exchangeType": 1, "tokens": ["3456"]}, {"exchangeType": 1, "tokens": ["910"]},
    {"exchangeType": 1, "tokens": ["2031"]}, {"exchangeType": 1, "tokens": ["14977"]},
    {"exchangeType": 1, "tokens": ["881"]}, {"exchangeType": 1, "tokens": ["5900"]},
    {"exchangeType": 1, "tokens": ["1348"]}, {"exchangeType": 1, "tokens": ["236"]},
    {"exchangeType": 1, "tokens": ["317"]}, {"exchangeType": 1, "tokens": ["3351"]},
    {"exchangeType": 1, "tokens": ["3432"]}, {"exchangeType": 1, "tokens": ["25"]},
    {"exchangeType": 1, "tokens": ["694"]}, {"exchangeType": 1, "tokens": ["2885"]},
    {"exchangeType": 1, "tokens": ["383"]}, {"exchangeType": 1, "tokens": ["4963"]},
    {"exchangeType": 1, "tokens": ["526"]}, {"exchangeType": 1, "tokens": ["547"]},
    {"exchangeType": 1, "tokens": ["3787"]}, {"exchangeType": 1, "tokens": ["4306"]},
    {"exchangeType": 1, "tokens": ["5258"]}, {"exchangeType": 1, "tokens": ["7229"]},
    {"exchangeType": 1, "tokens": ["3045"]}, {"exchangeType": 1, "tokens": ["3506"]},
    {"exchangeType": 1, "tokens": ["26009"]}
]
TOKENS = [t["tokens"][0] for t in token_list]

# ======================
# 🕒 TIME WINDOWS
# ======================
TIME_WINDOWS = [
    ("09:15", "09:30"),
    ("09:30", "10:30"),
    ("10:30", "14:30"),
    ("14:30", "15:15")
]

# ======================
# 📦 CONNECT TO AZURE
# ======================
blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

print(f"📂 Fetching CSV files from folder: {TODAY_FOLDER}")

# ======================
# 📥 STEP 1: DOWNLOAD & COMBINE ALL CSVs
# ======================
dataframes = []

for blob in container_client.list_blobs(name_starts_with=TODAY_FOLDER):
    if blob.name.endswith(".csv"):
        print(f"Loading: {blob.name}")
        blob_data = container_client.download_blob(blob.name).readall()
        df = pd.read_csv(io.BytesIO(blob_data))
        dataframes.append(df)

if not dataframes:
    raise ValueError(f"No CSV files found under folder {TODAY_FOLDER}")

combined_df = pd.concat(dataframes, ignore_index=True)
print(f"✅ Loaded {len(dataframes)} CSV files with {len(combined_df)} total rows.")

# ======================
# 🧹 STEP 2: CLEAN & FILTER DATA
# ======================
timestamp_col = "exchange_timestamp"
token_col = "token"
high_col = "high_price_of_the_day"
low_col = "low_price_of_the_day"

# Validate expected columns
for col in [timestamp_col, token_col, high_col, low_col]:
    if col not in combined_df.columns:
        raise KeyError(f"Expected column '{col}' not found in CSVs")

# Convert timestamp column to datetime
combined_df[timestamp_col] = pd.to_datetime(combined_df[timestamp_col])

# Filter for known tokens
combined_df = combined_df[combined_df[token_col].astype(str).isin(TOKENS)]

# ======================
# 📈 STEP 3: FIND HIGH/LOW FOR EACH TOKEN IN TIME WINDOWS
# ======================
summary_results = []

for start, end in TIME_WINDOWS:
    start_time = pd.to_datetime(start).time()
    end_time = pd.to_datetime(end).time()

    mask = combined_df[timestamp_col].dt.time.between(start_time, end_time)
    window_df = combined_df[mask]

    agg = window_df.groupby(token_col).agg(
        high_value=(high_col, 'max'),
        low_value=(low_col, 'min')
    ).reset_index()

    agg['time_range'] = f"{start}-{end}"
    summary_results.append(agg)

final_df = pd.concat(summary_results, ignore_index=True)

# ======================
# 💾 STEP 4: SAVE RESULT LOCALLY
# ======================
output_file = f"market_summary_{MANUAL_DATE}.csv"
final_df.to_csv(output_file, index=False)

print("\n✅ Summary file created successfully!")
print(f"📁 Local file: {output_file}")
print(f"🧾 Rows: {len(final_df)}")
