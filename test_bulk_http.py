"""
Direct HTTP test of the bulk upload API.
Logs in as admin, then uploads a test CSV.
Run: .\ven\Scripts\python.exe test_bulk_http.py
"""
import requests

BASE_URL = "http://localhost:5000/api"

# 1. Login
print("1. Logging in as admin...")
resp = requests.post(f"{BASE_URL}/auth/login", json={"username": "admin", "password": "admin"})
if resp.status_code != 200:
    print(f"Login FAILED: {resp.status_code} {resp.text}")
    exit(1)

token = resp.json()["access_token"]
print(f"   Token: {token[:30]}...")
headers = {"Authorization": f"Bearer {token}"}

# 2. Check existing rooms
print("\n2. Current rooms in DB:")
r = requests.get(f"{BASE_URL}/rooms", headers=headers)
print(f"   Status: {r.status_code}, Rooms: {r.json()}")

# 3. Upload rooms CSV
print("\n3. Uploading rooms CSV...")
csv_content = "name,capacity,room_type\nHTTPTest-Room-A,60,classroom\nHTTPTest-Lab-B,40,lab\n"
files = {"file": ("rooms_test.csv", csv_content.encode("utf-8"), "text/csv")}
data = {"target": "rooms"}
resp = requests.post(f"{BASE_URL}/bulk/upload", headers=headers, files=files, data=data)
print(f"   Status: {resp.status_code}")
print(f"   Response: {resp.json()}")

# 4. Check rooms after
print("\n4. Rooms after upload:")
r = requests.get(f"{BASE_URL}/rooms", headers=headers)
print(f"   Status: {r.status_code}, Rooms: {r.json()}")

# 5. Cleanup test rooms
print("\n5. Cleanup...")
for room in r.json():
    if room["name"].startswith("HTTPTest-"):
        del_resp = requests.delete(f"{BASE_URL}/rooms/{room['id']}", headers=headers)
        print(f"   Deleted {room['name']}: {del_resp.status_code}")

print("\nTest complete.")
