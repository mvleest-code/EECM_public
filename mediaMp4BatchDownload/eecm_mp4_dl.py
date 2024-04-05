import datetime
import os
import requests
import threading
from tqdm import tqdm

## script will download all the mp4 files from the camera for the given date range
## will request all downloads in parallel with a max of 10 concurrent downloads
## will print a summary of the downloads at the end
## will print the start and end timestamps of the first and last recording downloaded
## will print the total number of files downloaded
## files will be saved in the current working directory in a folder named after the camera_id
## each day's recordings will be saved in a subfolder named after the date in the format YYYY-MM-DD
## each file will be named after the camera_id, start time and end time of the recording

# add camera_id
camera_id = ""

# Define the range of days for the downloads
start_date = datetime.datetime(2024, 2, 23) # start date
end_date = datetime.datetime(2024, 3, 10)  # end date

# add access_token
access_token = ""

TIMESTAMP_FORMAT0 = "%3A"
TIMESTAMP_FORMAT1 = "%2B"

downloaded_files_count = 0
earliest_start_timestamp = None
latest_end_timestamp = None
lock = threading.Lock()  

semaphore = threading.Semaphore(10)

def format_timestamp(timestamp, format0, format1):
    """Formats the timestamp for the API request."""
    return timestamp.replace(":", format0).replace("+", format1)

def download_file(session, url, filename, headers):
    """Downloads a file and updates the progress bar."""
    with session.get(url, stream=True, headers=headers) as r:
        r.raise_for_status()
        total_size_in_bytes = int(r.headers.get('content-length', 0))
        block_size = 1024
        progress_bar = tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True, desc=f"Downloading {os.path.basename(filename)}")
        with open(filename, 'wb') as f:
            for data in r.iter_content(block_size):
                progress_bar.update(len(data))
                f.write(data)
        progress_bar.close()
        if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
            print("ERROR, something went wrong")
        return True 

def download_worker(access_token, cameraId, recordingId, filepath, start_time_str, end_time_str):
    """Worker function for downloading a single recording."""
    semaphore.acquire()
    global downloaded_files_count, earliest_start_timestamp, latest_end_timestamp
    try:
        url = f"http://rest.cameramanager.com/rest/v2.4/cameras/{cameraId}/recordings/{recordingId}?includeUrlTypes=mp4Http"
        headers = {"accept": "application/json", "Authorization": f"Bearer {access_token}"}
        session = requests.Session()
        response = session.get(url, headers=headers).json()
        download_url = response['urls']['mp4Http']  
        if download_file(session, download_url, filepath, headers):
            with lock:
                downloaded_files_count += 1
                if earliest_start_timestamp is None or start_time_str < earliest_start_timestamp:
                    earliest_start_timestamp = start_time_str
                if latest_end_timestamp is None or end_time_str > latest_end_timestamp:
                    latest_end_timestamp = end_time_str
    finally:
        semaphore.release()

def fetch_and_download_recordings(start_date, access_token, camera_id):
    """Fetches and downloads recordings for a given date."""
    end_date = start_date + datetime.timedelta(days=1)
    unencoded_startTimestamp = start_date.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    unencoded_endTimestamp = end_date.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
    startTimestamp = format_timestamp(unencoded_startTimestamp, TIMESTAMP_FORMAT0, TIMESTAMP_FORMAT1)
    endTimestamp = format_timestamp(unencoded_endTimestamp, TIMESTAMP_FORMAT0, TIMESTAMP_FORMAT1)

    url = f"http://rest.cameramanager.com/rest/v2.4/cameras/{camera_id}/recordings?minTimestamp={startTimestamp}&maxTimestamp={endTimestamp}&limit=200&sortByRecordingIdOrder=asc&slice=false"
    headers = {"accept": "application/json", "Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    recordings = response.json() 

    for recording in recordings:
        if 'startTime' in recording and 'endTime' in recording:
            start_time_str = recording['startTime']
            end_time_str = recording['endTime']
            filename = f"{camera_id}_{start_time_str}_{end_time_str}.mp4"

            directory = os.path.join(str(camera_id), start_date.strftime("%Y-%m-%d"))
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            filepath = os.path.join(directory, filename)
            download_worker(access_token, camera_id, recording['recordingId'], filepath, start_time_str, end_time_str)

current_date = start_date
while current_date < end_date:
    fetch_and_download_recordings(current_date, access_token, camera_id)
    current_date += datetime.timedelta(days=1)
    
print("Download summary:")
print(f"Total files downloaded: {downloaded_files_count}")
if earliest_start_timestamp and latest_end_timestamp:
    print(f"Start timestamp of the first recording: {earliest_start_timestamp}")
    print(f"End timestamp of the last recording: {latest_end_timestamp}")
