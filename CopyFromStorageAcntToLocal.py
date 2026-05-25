# This script copies all CSV files from an Azure Storage Account folder to a local directory
# No data transformation or consolidation is performed — files are saved as-is.

import os
from azure.storage.blob import BlobServiceClient

# ======================
# CONFIGURATION
# ======================
AZURE_CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=storageaccountdatarig;AccountKey=mlqWv0MzjNhM40m0Z26BOH556vg7n2oOEqdNm3BkxjtzBRwFGmSnYBZ+wm0kxY2mYOGe4FFjgSa3+AStN8sb/Q==;EndpointSuffix=core.windows.net"
CONTAINER_NAME = "stockdata"
FOLDER_NAME = "20260521"         # Azure folder (prefix) to copy from
LOCAL_OUTPUT_DIR = "C:\\Algo_trading\\cpp_code\\downloaded_stockdata\\"   # Local folder to copy into

# ======================
# COPY FILES FROM AZURE TO LOCAL
# ======================
def copy_blobs_to_local():
    os.makedirs(LOCAL_OUTPUT_DIR, exist_ok=True)

    service = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    container = service.get_container_client(CONTAINER_NAME)

    blobs = [b for b in container.list_blobs(name_starts_with=FOLDER_NAME) if b.name.endswith(".csv")]

    if not blobs:
        print("⚠️  No CSV files found in folder:", FOLDER_NAME)
        return

    print(f"Found {len(blobs)} CSV file(s). Starting download...\n")

    for blob in blobs:
        # Preserve sub-folder structure inside LOCAL_OUTPUT_DIR
        relative_path = blob.name  # e.g. "20260416/NIFTY_09:15.csv"
        safe_relative_path = relative_path.replace(":", "-")  # → "20260428/NIFTY_09-15.csv"
        safe_relative_path = relative_path.replace("/", "\\")  # → "20260428\\NIFTY_09-15.csv"
        local_file_path = os.path.join(LOCAL_OUTPUT_DIR, safe_relative_path)
  

        # Create any nested sub-directories if present
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

        print(f"Downloading: {blob.name}  →  {local_file_path}")
        raw_data = container.download_blob(blob.name).readall()

        with open(local_file_path, "wb") as f:
            f.write(raw_data)

    print(f"\n✅ All files copied to '{LOCAL_OUTPUT_DIR}'")

# ======================
# ENTRY POINT
# ======================
if __name__ == "__main__":
    copy_blobs_to_local()