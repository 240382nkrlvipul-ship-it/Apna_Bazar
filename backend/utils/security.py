import re

def sanitize_string(text):
    """
    Strips raw HTML tags and javascript nodes from input strings.
    """
    if not isinstance(text, str):
        return text
        
    # Remove script nodes completely
    text = re.sub(r'<script.*?>.*?</script.*?>', '', text, flags=re.IGNORECASE | re.DOTALL)
    # Remove any other HTML opening/closing/standalone tags
    text = re.sub(r'<[^>]*>', '', text)
    
    return text.strip()

def sanitize_data(data):
    """
    Recursively scans and sanitizes JSON structures (dicts, lists, strings).
    """
    if isinstance(data, dict):
        return {k: sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(x) for x in data]
    elif isinstance(data, str):
        return sanitize_string(data)
    return data
