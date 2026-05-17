import sys
import os
import base64
import json
import time
import google.generativeai as genai
from openai import OpenAI

# Robust path handling for standalone execution
def find_bench_root(start_path):
    path = os.path.abspath(start_path)
    while path != os.path.dirname(path):
        if os.path.exists(os.path.join(path, "sites")) and os.path.exists(os.path.join(path, "apps")):
            return path
        path = os.path.dirname(path)
    return None

current_path = os.path.dirname(os.path.abspath(__file__))
bench_root = find_bench_root(current_path)
if not bench_root:
    raise RuntimeError("Could not find frappe-bench root directory")

apps_path = os.path.join(bench_root, "apps")
sites_path = os.path.join(bench_root, "sites")

if apps_path not in sys.path:
    sys.path.insert(0, os.path.join(apps_path, "frappe"))
    sys.path.insert(0, os.path.join(apps_path, "flamezo_backend"))

import frappe
from flamezo_backend.flamezo.services.ai.menu_extraction import MenuExtractor, MenuExtractionResult

def vision_chain_gemini_test(image_path):
    os.chdir(sites_path)
    frappe.init(site="dine_matters", sites_path=".")
    frappe.connect()
    
    # API Keys
    OPENAI_KEY = frappe.conf.get("openai_api_key")
    GEMINI_KEY = frappe.conf.get("gemini_api_key")

    genai.configure(api_key=GEMINI_KEY)
    gemini_model = genai.GenerativeModel("models/gemini-2.5-flash")
    openai_client = OpenAI(api_key=OPENAI_KEY)

    extractor = MenuExtractor()
    with open(image_path, "rb") as f:
        img_data = f.read()
        base64_image = base64.b64encode(img_data).decode('utf-8')
    
    # STAGE 0: Layout Profiler (The Surveyor)
    print("STAGE 0: Analyzing layout with Gemini 2.5 Flash...")
    profiler_prompt = (
        "TASK: PREPARE A TRANSCRIPTION PLAN\n\n"
        "Analyze this menu image carefully. You need to describe its structural layout so a transcriber can extract it with 100% accuracy.\n"
        "1. Identify the structural pattern (e.g., Multi-column grid, horizontal list, or dense sections).\n"
        "2. Identify pricing alignment (e.g., 'Full' and 'Half' headers, or inline variants like '100 200').\n"
        "3. Provide FIRM RULES for a transcriber to follow to prevent row-drifting.\n"
        "OUTPUT ONLY THE RULES. No meta-talk."
    )
    
    response = gemini_model.generate_content([profiler_prompt, {"mime_type": "image/png", "data": base64_image}])
    plan = response.text
    print("--- TRANSCRIPTION PLAN GENERATED ---")
    
    # STAGE 1: Custom Forensic Transcription (The Transcriber)
    print("\nSTAGE 1: Transcribing layout with Gemini 2.5 Flash...")
    ocr_prompt = (
        f"You are a forensic OCR agent. Follow these rules strictly to transcribe the menu into a high-fidelity text grid:\n\n"
        f"{plan}\n\n"
        f"Output ONLY the resulting grid. No markdown formatting, just the text layout."
    )
    
    response = gemini_model.generate_content([ocr_prompt, {"mime_type": "image/png", "data": base64_image}])
    raw_transcription = response.text
    print("--- VISUAL TRANSCRIPTION COMPLETED ---")
    
    # Save transcription
    img_name = os.path.basename(image_path).split('.')[0]
    output_dir = os.path.dirname(os.path.abspath(__file__))
    trans_file = os.path.join(output_dir, f"transcription_gemini_{img_name}.txt")
    with open(trans_file, "w") as f:
        f.write(raw_transcription)
    
    # STAGE 2: Semantic Reconstruction (The Architect)
    print("\nSTAGE 2: Reconstructing Menu JSON...")
    system_prompt = extractor._get_extraction_prompt()
    user_prompt = (
        f"You are provided with a high-fidelity spatial transcription of a menu:\n\n"
        f"```text\n{raw_transcription}\n```\n\n"
        f"TASK: Reconstruct the complete menu JSON using this grid and the original image as context.\n"
        f"Use spatial reasoning to map all prices and variants correctly."
    )

    final_response = openai_client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "high"}}
                ]
            }
        ],
        response_format=MenuExtractionResult,
        temperature=0.0
    )
    
    result = final_response.choices[0].message.parsed
    
    # Save result
    result_file = os.path.join(output_dir, f"vision_chain_gemini_{img_name}_result.json")
    with open(result_file, "w") as f:
        json.dump(result.model_dump(), f, indent=2)
    
    print(f"\nDone. Saved to {result_file}")
    print(f"Extracted {len(result.dishes)} dishes.")
    print(f"Dishes with customizations: {len([d for d in result.dishes if d.customizationQuestions])}")
    
    # Validation
    for d in result.dishes:
        if "Open Shawarma" in d.name:
            prices = [o.price for q in d.customizationQuestions for o in q.options]
            print(f"CHECK [Open Shawarma]: Base Price: {d.price}, Options: {prices}")

    frappe.destroy()

def run_all_tests():
    images = [
        "/home/frappe/frappe-bench/apps/flamezo_backend/menu images/menu1.png",
        "/home/frappe/frappe-bench/apps/flamezo_backend/menu images/menu2.png",
        "/home/frappe/frappe-bench/apps/flamezo_backend/menu images/menu3.png"
    ]
    
    for i, img in enumerate(images, 1):
        print(f"\n{'='*50}")
        print(f"TESTING IMAGE {i}: {img}")
        print(f"{'='*50}")
        try:
            vision_chain_gemini_test(img)
        except Exception as e:
            print(f"Error processing {img}: {e}")

if __name__ == "__main__":
    run_all_tests()
