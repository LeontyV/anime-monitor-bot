"""
Speech-to-text module using Speechmatics API.
"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

SPEECHMATICS_API_KEY = os.getenv('SPEECHMATICS_API_KEY')
SPEECHMATICS_API_URL = "https://asr.api.speechmatics.com/v2"

def transcribe_audio(audio_path_or_url, language="ru"):
    """
    Transcribe audio file using Speechmatics API.
    
    Args:
        audio_path_or_url: Path to audio file or URL
        language: Language code (default: ru for Russian)
    
    Returns:
        str: Transcribed text
    """
    if not SPEECHMATICS_API_KEY:
        raise ValueError("SPEECHMATICS_API_KEY not set in .env")
    
    # For URL mode (Telegram voice messages are URLs)
    if audio_path_or_url.startswith("http"):
        # Use URL mode
        return transcribe_url(audio_path_or_url, language)
    else:
        # Use file mode
        return transcribe_file(audio_path_or_url, language)

def transcribe_file(audio_path, language="ru"):
    """Transcribe a local audio file."""
    
    # Detect file type
    if audio_path.endswith('.ogg'):
        content_type = 'audio/ogg'
    elif audio_path.endswith('.mp3'):
        content_type = 'audio/mpeg'
    elif audio_path.endswith('.wav'):
        content_type = 'audio/wav'
    else:
        content_type = 'audio/ogg'
    
    with open(audio_path, 'rb') as f:
        audio_data = f.read()
    
    # Build transcription request
    url = f"{SPEECHMATICS_API_URL}/transcriptions"
    
    files = {
        'audio_file': (os.path.basename(audio_path), audio_data, content_type)
    }
    
    data = {
        'language': language,
        'operating_point': 'standard',
    }
    
    headers = {
        'Authorization': f'Bearer {SPEECHMATICS_API_KEY}'
    }
    
    response = requests.post(url, files=files, data=data, headers=headers, timeout=120)
    
    if response.status_code != 200:
        raise Exception(f"Speechmatics API error: {response.status_code} - {response.text}")
    
    result = response.json()
    return parse_transcription_result(result)

def transcribe_url(audio_url, language="ru"):
    """Transcribe audio from URL."""
    
    url = f"{SPEECHMATICS_API_URL}/transcriptions"
    
    data = {
        'language': language,
        'operating_point': 'standard',
        'audio_url': audio_url,
    }
    
    headers = {
        'Authorization': f'Bearer {SPEECHMATICS_API_KEY}'
    }
    
    response = requests.post(url, json=data, headers=headers, timeout=120)
    
    if response.status_code != 200:
        raise Exception(f"Speechmatics API error: {response.status_code} - {response.text}")
    
    result = response.json()
    
    # Poll for completion
    transcription_id = result.get('id')
    if transcription_id:
        return poll_transcription(transcription_id, language)
    
    return parse_transcription_result(result)

def poll_transcription(transcription_id, language="ru", max_wait=120):
    """Poll for transcription completion."""
    import time
    
    url = f"{SPEECHMATICS_API_URL}/transcriptions/{transcription_id}"
    headers = {
        'Authorization': f'Bearer {SPEECHMATICS_API_KEY}'
    }
    
    elapsed = 0
    while elapsed < max_wait:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            raise Exception(f"Polling error: {response.status_code}")
        
        result = response.json()
        status = result.get('status')
        
        if status == 'completed':
            return parse_transcription_result(result)
        elif status == 'failed':
            raise Exception(f"Transcription failed: {result}")
        
        time.sleep(2)
        elapsed += 2
    
    raise Exception(f"Transcription timed out after {max_wait}s")

def parse_transcription_result(result):
    """Parse Speechmatics response to extract text."""
    if 'transaction' in result:
        # Async/URL mode result
        if 'result' in result['transaction']:
            return result['transaction']['result'].get('text', '')
        if 'status' in result:
            if result['status'] == 'completed' and 'result' in result:
                return result['result'].get('text', '')
    elif 'results' in result:
        # Sync/file mode result
        texts = []
        for item in result['results']:
            if 'alternatives' in item:
                texts.append(item['alternatives'][0].get('content', ''))
        return ' '.join(texts)
    return ''

if __name__ == '__main__':
    # Test
    import sys
    if len(sys.argv) > 1:
        text = transcribe_audio(sys.argv[1])
        print(f"Transcription: {text}")
