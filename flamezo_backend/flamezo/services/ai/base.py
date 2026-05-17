import frappe
from openai import OpenAI
import anthropic
import google.generativeai as genai

def get_openai_client():
    """Initialize OpenAI client using frappe.conf"""
    api_key = frappe.conf.get("openai_api_key")
    if not api_key:
        # Fallback to site_config if not in common_site_config
        api_key = frappe.get_conf().get("openai_api_key")
        
    if not api_key:
        frappe.throw("OpenAI API Key not found in site configuration (openai_api_key)")
    
    return OpenAI(api_key=api_key)

def get_anthropic_client():
    """Initialize Anthropic client using frappe.conf"""
    api_key = frappe.conf.get("anthropic_api_key")
    if not api_key:
        api_key = frappe.get_conf().get("anthropic_api_key")
        
    if not api_key:
        frappe.throw("Anthropic API Key not found in site configuration (anthropic_api_key)")
        
    
    return anthropic.Anthropic(api_key=api_key)

def get_gemini_client():
    """Initialize Gemini client using frappe.conf"""
    api_key = frappe.conf.get("gemini_api_key")
    if not api_key:
        api_key = frappe.get_conf().get("gemini_api_key")
        
    if not api_key:
        frappe.throw("Gemini API Key not found in site configuration (gemini_api_key)")
        
    genai.configure(api_key=api_key)
    return genai.GenerativeModel("models/gemini-2.5-flash")

def handle_ai_error(e):
    """Standardized error handling for AI services with specific provider error mapping"""
    import openai
    import anthropic
    
    error_msg = str(e)
    title = "AI Service Error"
    
    if isinstance(e, openai.RateLimitError):
        error_msg = "OpenAI API Quota Exceeded. Please check your billing/plan or wait a few minutes."
        title = "Rate Limit Reached"
    elif isinstance(e, openai.AuthenticationError):
        error_msg = "Invalid OpenAI API Key. Please verify the key in your site configuration."
        title = "Authentication Failed"
    elif isinstance(e, openai.APIConnectionError):
        error_msg = "Disconnected from OpenAI. The service might be temporarily unreachable."
        title = "Connection Error"
    elif isinstance(e, openai.APIStatusError):
        error_msg = f"OpenAI Service Error (Status {e.status_code}). Please try again later."
        title = "Service Error"
    elif isinstance(e, anthropic.RateLimitError):
        error_msg = "Anthropic API Quota Exceeded. Please check your plan."
        title = "Rate Limit Reached"
    elif "403" in error_msg and "Gemini" in error_msg:
        error_msg = "Gemini API Key blocked or invalid permissions."
        title = "Authentication Failed"
    elif "429" in error_msg and "Gemini" in error_msg:
        error_msg = "Gemini API Quota Exceeded."
        title = "Rate Limit Reached"
    
    frappe.log_error(frappe.get_traceback(), title)
    
    return {
        "success": False,
        "error": error_msg,
        "message": error_msg,
        "title": title
    }
