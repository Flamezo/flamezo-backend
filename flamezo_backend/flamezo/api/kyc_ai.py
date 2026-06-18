import frappe
from flamezo_backend.flamezo.services.ai.base import get_openai_client, handle_ai_error
import base64
import json
import os

@frappe.whitelist()
def extract_bank_details(base64_image=None):
    try:
        if not base64_image:
            frappe.throw("base64_image is required")
            
        # Strip data URL prefix if present (e.g. data:image/jpeg;base64,...)
        if "base64," in base64_image:
            base64_image = base64_image.split("base64,")[1]
            
        client = get_openai_client()
        
        prompt = """
        You are a highly accurate OCR assistant for a financial platform. 
        Extract the following exact details from the provided cancelled cheque or bank statement:
        1. "account_number": The exact bank account number.
        2. "ifsc_code": The exact 11-character IFSC code.
        3. "legal_business_name": The exact name printed on the cheque for the account holder (often found near "For <Name>" or at the bottom right).
        
        Return ONLY a raw JSON object. Do NOT wrap it in markdown code blocks like ```json. Just the JSON.
        Example: {"account_number": "1234567890", "ifsc_code": "HDFC0001234", "legal_business_name": "JOHN DOE"}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=300
        )
        
        content = response.choices[0].message.content.strip()
        if content.startswith('```json'):
            content = content[7:-3].strip()
        elif content.startswith('```'):
            content = content[3:-3].strip()
            
        data = json.loads(content)
        return {
            "success": True,
            "data": data
        }
    except Exception as e:
        return handle_ai_error(e)
