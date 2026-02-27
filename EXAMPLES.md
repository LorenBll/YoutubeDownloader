# YoutubeDownloader - Usage Examples

Practical examples for using the YoutubeDownloader API service.

## Table of Contents

- [Basic Usage](#basic-usage)
- [Single Video Downloads](#single-video-downloads)
- [Batch Downloads](#batch-downloads)
- [Python Client Examples](#python-client-examples)
- [cURL Examples](#curl-examples)
- [JavaScript/Node.js Examples](#javascriptnodejs-examples)
- [Common Use Cases](#common-use-cases)
- [Error Handling](#error-handling)

## Basic Usage

### Starting the Service

**Development (verbose mode):**
```bash
# Windows
scripts\run.bat --verbose

# macOS/Linux
./scripts/run.sh --verbose
```

**Background mode:**
```bash
# Windows
scripts\run.bat

# macOS/Linux
./scripts/run.sh
```

### Health Check

Verify the service is running:
```bash
curl http://localhost:49153/api/health
```

Response:
```json
{
  "status": "ok",
  "bind": "127.0.0.1",
  "port": 49153,
  "task_counts": {
    "queued": 0,
    "in_progress": 0,
    "completed": 2,
    "failed": 0,
    "total": 2
  },
  "task_retention_minutes": 30,
  "task_cleanup_interval_seconds": 60,
  "youtube_client": "pytubefix"
}
```

## Single Video Downloads

### MP4 Video Download (720p)

```bash
curl -X POST http://localhost:49153/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "video_link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "mp4",
    "quality": "720p",
    "folder": "/Users/username/Downloads"
  }'
```

Response:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued"
}
```

### MP3 Audio Download (128kbps)

```bash
curl -X POST http://localhost:49153/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "video_link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "mp3",
    "quality": "128kbps",
    "folder": "/Users/username/Music",
    "name": "My Favorite Song"
  }'
```

### Custom Filename

```bash
curl -X POST http://localhost:49153/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "video_link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "mp4",
    "quality": "1080p",
    "folder": "C:\\Users\\username\\Videos",
    "name": "Custom Video Name"
  }'
```

### Check Task Status

```bash
curl http://localhost:49153/api/download/550e8400-e29b-41d4-a716-446655440000
```

**While in progress:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "in_progress"
}
```

**When completed:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "name": "Video Title",
    "format": "mp4",
    "requested_quality": "720p",
    "actual_quality": "720p",
    "save_path": "/Users/username/Downloads/Video Title.mp4"
  }
}
```

**If failed:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error": "YouTube request failed while fetching available mp4 streams."
}
```

## Batch Downloads

Download multiple videos in one request:

```bash
curl -X POST http://localhost:49153/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "videos": [
      {
        "video_link": "https://www.youtube.com/watch?v=video1",
        "format": "mp4",
        "quality": "720p",
        "folder": "/Users/username/Downloads"
      },
      {
        "video_link": "https://www.youtube.com/watch?v=video2",
        "format": "mp3",
        "quality": "192kbps",
        "folder": "/Users/username/Music"
      },
      {
        "video_link": "https://www.youtube.com/watch?v=video3",
        "format": "mp4",
        "quality": "1080p",
        "folder": "/Users/username/Downloads",
        "name": "Custom Name"
      }
    ]
  }'
```

Response:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "queued",
  "video_count": 3
}
```

Batch task result:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440001",
  "status": "completed",
  "result": {
    "items": [
      {
        "index": 0,
        "status": "completed",
        "result": {
          "name": "Video 1 Title",
          "format": "mp4",
          "requested_quality": "720p",
          "actual_quality": "720p",
          "save_path": "/Users/username/Downloads/Video 1 Title.mp4"
        }
      },
      {
        "index": 1,
        "status": "completed",
        "result": {
          "name": "Video 2 Title",
          "format": "mp3",
          "requested_quality": "192kbps",
          "actual_quality": "192kbps",
          "save_path": "/Users/username/Music/Video 2 Title.mp3"
        }
      },
      {
        "index": 2,
        "status": "failed",
        "error": "No mp4 progressive streams are available for this video."
      }
    ],
    "summary": {
      "total": 3,
      "completed": 2,
      "failed": 1
    }
  }
}
```

## Python Client Examples

### Simple Download Script

```python
import requests
import time
import json

API_BASE = "http://localhost:49153"

def download_video(video_url, format="mp4", quality="720p", folder="./downloads"):
    """Download a YouTube video."""
    # Create download task
    response = requests.post(
        f"{API_BASE}/api/download",
        json={
            "video_link": video_url,
            "format": format,
            "quality": quality,
            "folder": folder
        }
    )
    response.raise_for_status()
    task_id = response.json()["task_id"]
    print(f"Task created: {task_id}")
    
    # Poll for completion
    while True:
        response = requests.get(f"{API_BASE}/api/download/{task_id}")
        response.raise_for_status()
        task = response.json()
        status = task["status"]
        
        print(f"Status: {status}")
        
        if status == "completed":
            print(f"Downloaded: {task['result']['save_path']}")
            return task["result"]
        elif status == "failed":
            print(f"Failed: {task['error']}")
            raise Exception(task["error"])
        
        time.sleep(2)  # Wait 2 seconds before checking again

# Usage
if __name__ == "__main__":
    download_video(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        format="mp4",
        quality="720p",
        folder="/Users/username/Downloads"
    )
```

### Batch Download Script

```python
import requests
import time

API_BASE = "http://localhost:49153"

def batch_download(video_list):
    """Download multiple videos."""
    # Create batch task
    response = requests.post(
        f"{API_BASE}/api/download",
        json={"videos": video_list}
    )
    response.raise_for_status()
    task_id = response.json()["task_id"]
    print(f"Batch task created: {task_id}")
    
    # Poll for completion
    while True:
        response = requests.get(f"{API_BASE}/api/download/{task_id}")
        response.raise_for_status()
        task = response.json()
        status = task["status"]
        
        if status == "completed":
            result = task["result"]
            summary = result["summary"]
            print(f"\nBatch complete:")
            print(f"  Total: {summary['total']}")
            print(f"  Completed: {summary['completed']}")
            print(f"  Failed: {summary['failed']}")
            
            for item in result["items"]:
                if item["status"] == "completed":
                    print(f"  ✓ {item['result']['name']}")
                else:
                    print(f"  ✗ Index {item['index']}: {item['error']}")
            
            return result
        elif status == "failed":
            print(f"Failed: {task['error']}")
            raise Exception(task["error"])
        
        time.sleep(3)

# Usage
videos = [
    {
        "video_link": "https://www.youtube.com/watch?v=video1",
        "format": "mp4",
        "quality": "720p",
        "folder": "./downloads"
    },
    {
        "video_link": "https://www.youtube.com/watch?v=video2",
        "format": "mp3",
        "quality": "128kbps",
        "folder": "./music"
    }
]

batch_download(videos)
```

### With Unprivate Mode (API Key)

```python
import requests

API_BASE = "http://192.168.1.100:49153"
API_KEY = "your-secret-api-key"

def download_with_auth(video_url):
    """Download with API key authentication."""
    response = requests.post(
        f"{API_BASE}/api/download",
        json={
            "api_key": API_KEY,
            "video_link": video_url,
            "format": "mp4",
            "quality": "720p",
            "folder": "./downloads"
        }
    )
    response.raise_for_status()
    return response.json()

# Or pass in query string
response = requests.post(
    f"{API_BASE}/api/download?api_key={API_KEY}",
    json={
        "video_link": video_url,
        "format": "mp4",
        "quality": "720p",
        "folder": "./downloads"
    }
)
```

## JavaScript/Node.js Examples

### Simple Download (Node.js)

```javascript
const axios = require('axios');

const API_BASE = 'http://localhost:49153';

async function downloadVideo(videoUrl, format = 'mp4', quality = '720p', folder = './downloads') {
  // Create task
  const createResponse = await axios.post(`${API_BASE}/api/download`, {
    video_link: videoUrl,
    format: format,
    quality: quality,
    folder: folder
  });
  
  const taskId = createResponse.data.task_id;
  console.log(`Task created: ${taskId}`);
  
  // Poll for completion
  while (true) {
    const statusResponse = await axios.get(`${API_BASE}/api/download/${taskId}`);
    const task = statusResponse.data;
    const status = task.status;
    
    console.log(`Status: ${status}`);
    
    if (status === 'completed') {
      console.log(`Downloaded: ${task.result.save_path}`);
      return task.result;
    } else if (status === 'failed') {
      throw new Error(task.error);
    }
    
    // Wait 2 seconds
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
}

// Usage
downloadVideo('https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'mp4', '720p', '/Users/username/Downloads')
  .then(result => console.log('Download complete:', result))
  .catch(error => console.error('Download failed:', error));
```

## Common Use Cases

### High Quality Video (1080p with FFmpeg)

Downloads videos at 1080p or higher, which requires FFmpeg for audio/video merging:

```bash
curl -X POST http://localhost:49153/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "video_link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "mp4",
    "quality": "1080p",
    "folder": "/Users/username/Videos"
  }'
```

Result will include `"merge": "ffmpeg"` to indicate merging was used.

### Extract Audio Only

```bash
curl -X POST http://localhost:49153/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "video_link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "mp3",
    "quality": "192kbps",
    "folder": "/Users/username/Music"
  }'
```

### Download to Network Share (Windows)

```bash
curl -X POST http://localhost:49153/api/download \
  -H "Content-Type: application/json" \
  -d '{
    "video_link": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "format": "mp4",
    "quality": "720p",
    "folder": "\\\\NAS\\Videos"
  }'
```

## Error Handling

### Common Errors

**Invalid URL:**
```json
{
  "error": "video_link must be a valid YouTube URL (youtube.com or youtu.be)."
}
```

**Playlist URLs:**
```json
{
  "error": "Playlist download is not supported. Please provide a single video URL."
}
```

**Missing Fields:**
```json
{
  "error": "Missing required fields.",
  "missing_fields": ["video_link", "format"]
}
```

**Invalid Format:**
```json
{
  "error": "format must be either 'mp4' or 'mp3'"
}
```

**Quality Not Available:**
```json
{
  "task_id": "...",
  "status": "failed",
  "error": "No mp4 progressive streams are available for this video."
}
```

**Permission Denied:**
```json
{
  "task_id": "...",
  "status": "failed",
  "error": "Cannot write mp4 file to '/restricted/path'. Check disk space, permissions, or folder path."
}
```

**Authentication Required (Unprivate Mode):**
```json
{
  "error": "Authentication required. Provide api_key in JSON body or query string."
}
```

**Invalid API Key:**
```json
{
  "error": "Invalid API key."
}
```

## Tips and Best Practices

1. **Check health endpoint first** to ensure service is running
2. **Poll status every 2-5 seconds** - don't hammer the API
3. **Handle failed tasks gracefully** - some videos may not be downloadable
4. **Use batch downloads** for multiple videos to reduce overhead
5. **Specify folders with absolute paths** for clarity
6. **Check disk space** before large downloads
7. **For high quality videos (>720p)**, ensure FFmpeg is installed
8. **Use custom names** to organize downloads
9. **In batch mode**, some videos may succeed while others fail
10. **Tasks are retained for 30 minutes** by default, then cleaned up

## Troubleshooting

**Service not responding:**
- Check if service is running: `curl http://localhost:49153/api/health`
- Check configuration port in `resources/configuration.json`
- Ensure no firewall is blocking the port

**Downloads failing:**
- Verify the YouTube URL is correct and the video is available
- Check folder exists and has write permissions
- Ensure enough disk space
- For >720p, verify FFmpeg is installed: `ffmpeg -version`

**Quality not available:**
- Try a different quality (720p is most reliable)
- Some videos don't have all qualities
- The service will select the closest available quality

**Batch downloads timing out:**
- Batch downloads process sequentially
- Large batches may take time
- Consider splitting into smaller batches

For more help, see the [main README](README.md) or check the [troubleshooting section](README.md#troubleshooting).
