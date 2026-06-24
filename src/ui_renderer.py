import json
import sys
from pathlib import Path
from src.models.manifest import AppManifest
from src.models.schema import UIComponentType

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{app_name} - UI Preview</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background-color: #f3f4f6; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
        .glass-panel {{ background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.2); box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); }}
    </style>
</head>
<body class="min-h-screen flex flex-col">
    <!-- Navbar -->
    <nav class="bg-indigo-600 text-white p-4 shadow-md">
        <div class="container mx-auto flex justify-between items-center">
            <h1 class="text-2xl font-bold tracking-tight">{app_name}</h1>
            <div class="space-x-4">
                {nav_links}
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main class="container mx-auto p-6 flex-grow">
        <div class="mb-8">
            <h2 class="text-3xl font-extrabold text-gray-900 mb-2">{page_title}</h2>
            <p class="text-gray-500">Preview generated from AppForge UI Schema</p>
        </div>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            {components_html}
        </div>
    </main>
    
    <footer class="bg-gray-800 text-gray-300 p-4 text-center mt-auto">
        <p>AppForge Multi-Stage Pipeline - UI Preview</p>
    </footer>
</body>
</html>
"""

def render_form_field(field):
    input_type = field.input_type or "text"
    if input_type == "textarea":
        return f"""
        <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
            <textarea class="w-full border-gray-300 rounded-md shadow-sm p-2 border focus:ring-indigo-500 focus:border-indigo-500" rows="3" placeholder="Enter {field.label.lower()}"></textarea>
        </div>"""
    else:
        return f"""
        <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
            <input type="{input_type}" class="w-full border-gray-300 rounded-md shadow-sm p-2 border focus:ring-indigo-500 focus:border-indigo-500" placeholder="Enter {field.label.lower()}">
        </div>"""

def render_component(comp):
    html = f'<div class="glass-panel p-6 rounded-xl">'
    html += f'<h3 class="text-xl font-bold text-gray-800 mb-4 pb-2 border-b">{comp.title}</h3>'
    
    if comp.component_type == UIComponentType.FORM:
        html += '<form onsubmit="event.preventDefault(); alert(\'Form submitted (simulation)\')">'
        for field in (comp.form_fields or []):
            html += render_form_field(field)
        html += '<button type="submit" class="w-full bg-indigo-600 text-white font-medium py-2 px-4 rounded-md hover:bg-indigo-700 transition">Submit</button>'
        html += '</form>'
        
    elif comp.component_type == UIComponentType.TABLE:
        html += """
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">ID</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Data</th><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th></tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-200">
                    <tr><td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">1</td><td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">Sample Row A</td><td class="px-6 py-4 whitespace-nowrap"><span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">Active</span></td></tr>
                    <tr><td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">2</td><td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">Sample Row B</td><td class="px-6 py-4 whitespace-nowrap"><span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800">Pending</span></td></tr>
                </tbody>
            </table>
        </div>
        """
        
    elif comp.component_type == UIComponentType.LIST:
        html += '<ul class="space-y-3">'
        html += '<li class="bg-gray-50 p-3 rounded shadow-sm border border-gray-100">Item 1 Preview</li>'
        html += '<li class="bg-gray-50 p-3 rounded shadow-sm border border-gray-100">Item 2 Preview</li>'
        html += '<li class="bg-gray-50 p-3 rounded shadow-sm border border-gray-100">Item 3 Preview</li>'
        html += '</ul>'
        
    elif comp.component_type == UIComponentType.CHART:
        html += '<div class="h-48 bg-indigo-50 border border-indigo-100 rounded-lg flex items-center justify-center text-indigo-400 font-medium">[ Chart Visualization Preview ]</div>'
        
    elif comp.component_type == UIComponentType.METRICS_CARDS:
        html += """
        <div class="grid grid-cols-2 gap-4">
            <div class="bg-indigo-50 p-4 rounded-lg border border-indigo-100"><p class="text-sm text-indigo-500 font-medium">Metric 1</p><p class="text-2xl font-bold text-indigo-700">1,234</p></div>
            <div class="bg-green-50 p-4 rounded-lg border border-green-100"><p class="text-sm text-green-500 font-medium">Metric 2</p><p class="text-2xl font-bold text-green-700">98%</p></div>
        </div>
        """
    else:
        html += f'<div class="p-4 bg-gray-100 rounded text-gray-500 text-center italic">[{comp.component_type.value} component placeholder]</div>'
        
    html += '</div>'
    return html


def generate_preview(manifest_path: str):
    path = Path(manifest_path)
    if not path.exists():
        print(f"Error: Manifest {manifest_path} not found.")
        sys.exit(1)
        
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    manifest = AppManifest.model_validate(data)
    
    app_name = manifest.intent.app_name.replace('_', ' ').title()
    pages = manifest.ui_schema.pages
    
    if not pages:
        print("No pages found in UI Schema to render.")
        sys.exit(1)
        
    # Render navigation links for all pages
    nav_links = ""
    for p in pages:
        nav_links += f'<a href="#" class="hover:text-indigo-200 transition font-medium">{p.title}</a>\n'
        
    # Render the first page as the preview
    preview_page = pages[0]
    
    components_html = ""
    for comp in preview_page.components:
        components_html += render_component(comp)
        
    final_html = HTML_TEMPLATE.format(
        app_name=app_name,
        nav_links=nav_links,
        page_title=preview_page.title,
        components_html=components_html
    )
    
    output_path = path.parent / f"{path.stem}_preview.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_html)
        
    print(f"UI Preview successfully generated: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.ui_renderer <manifest_path>")
        sys.exit(1)
    generate_preview(sys.argv[1])
