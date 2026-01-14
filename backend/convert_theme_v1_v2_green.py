import json

# Input JSON from user (Corrected Boolean types for Python)
v1_data = {
  "ROOT": {
    "created": "2026-01-05",
    "bezeichnung": "Green Theme",
    "description": "Green Theme color scheme"
  },
  "dark": {
    "colors": {
      "info": "#42a5f5",
      "text": {
        "inverse": "#212121",
        "primary": "#ffffff",
        "disabled": "#6a6a6a",
        "secondary": "#b0b0b0",
        "on_tertiary": "#333333",
        "on_secondary": "#000000"
      },
      "error": "#ef5350",
      "border": {
        "dark": "#4a6a4a",
        "light": "#2a4a2a",
        "medium": "#3a5a3a"
      },
      "neutral": {
        "50": "#1a1a1a",
        "100": "#2a2a2a",
        "200": "#3a3a3a",
        "300": "#4a4a4a",
        "400": "#6a6a6a",
        "500": "#8a8a8a",
        "600": "#aaaaaa",
        "700": "#cacaca",
        "800": "#e0e0e0",
        "900": "#f5f5f5"
      },
      "primary": {
        "50": "#e8f5e9",
        "100": "#c8e6c9",
        "200": "#a5d6a7",
        "300": "#81c784",
        "400": "#66bb6a",
        "500": "#66bb6a",
        "600": "#43a047",
        "700": "#388e3c",
        "800": "#2e7d32",
        "900": "#1b5e20"
      },
      "success": "#66bb6a",
      "warning": "#ffb74d",
      "secondary": {
        "50": "#f3e5f5",
        "100": "#e1bee7",
        "200": "#ce93d8",
        "300": "#ba68c8",
        "400": "#ab47bc",
        "500": "#ba68c8",
        "600": "#8e24aa",
        "700": "#7b1fa2",
        "800": "#6a1b9a",
        "900": "#4a148c"
      },
      "background": {
        "primary": "#121212",
        "tertiary": "#2a2a2a",
        "secondary": "#1e1e1e"
      }
    },
    "typography": {
      "fontSize": {
        "lg": "1.125rem",
        "sm": "0.875rem",
        "xl": "1.25rem",
        "xs": "0.75rem",
        "2xl": "1.5rem",
        "3xl": "1.875rem",
        "4xl": "2.25rem",
        "base": "1rem",
        "scale": 1
      },
      "fontFamily": {
        "mono": "'Fira Code', 'Courier New', monospace",
        "primary": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "secondary": "Georgia, serif"
      },
      "fontWeight": {
        "bold": 700,
        "light": 300,
        "medium": 500,
        "normal": 400,
        "semibold": 600
      },
      "lineHeight": {
        "tight": 1.25,
        "normal": 1.5,
        "relaxed": 1.75
      }
    },
    "customizations": {
      "shadows": {
        "enabled": True,
        "intensity": "medium"
      },
      "animations": {
        "easing": "cubic-bezier(0.4, 0, 0.2, 1)",
        "enabled": True,
        "duration": "200ms"
      },
      "borderRadius": {
        "lg": "12px",
        "md": "8px",
        "sm": "4px",
        "full": "9999px"
      }
    }
  },
  "light": {
    "colors": {
      "info": "#2196f3",
      "text": {
        "inverse": "#ffffff",
        "primary": "#1b5e20",
        "disabled": "#bdbdbd",
        "secondary": "#616161",
        "on_tertiary": "#333333",
        "on_secondary": "#ffffff"
      },
      "error": "#f44336",
      "border": {
        "dark": "#81c784",
        "light": "#c8e6c9",
        "medium": "#a5d6a7"
      },
      "neutral": {
        "50": "#fafafa",
        "100": "#f5f5f5",
        "200": "#eeeeee",
        "300": "#e0e0e0",
        "400": "#bdbdbd",
        "500": "#9e9e9e",
        "600": "#757575",
        "700": "#616161",
        "800": "#424242",
        "900": "#212121"
      },
      "primary": {
        "50": "#e8f5e9",
        "100": "#c8e6c9",
        "200": "#a5d6a7",
        "300": "#81c784",
        "400": "#66bb6a",
        "500": "#4caf50",
        "600": "#43a047",
        "700": "#388e3c",
        "800": "#2e7d32",
        "900": "#1b5e20"
      },
      "success": "#4caf50",
      "warning": "#ff9800",
      "secondary": {
        "50": "#f3e5f5",
        "100": "#e1bee7",
        "200": "#ce93d8",
        "300": "#ba68c8",
        "400": "#ab47bc",
        "500": "#9c27b0",
        "600": "#8e24aa",
        "700": "#7b1fa2",
        "800": "#6a1b9a",
        "900": "#4a148c"
      },
      "background": {
        "primary": "#fafafa",
        "tertiary": "#e5e5e5",
        "secondary": "#f0f0f0"
      }
    },
    "typography": {
      "fontSize": {
        "lg": "1.125rem",
        "sm": "0.875rem",
        "xl": "1.25rem",
        "xs": "0.75rem",
        "2xl": "1.5rem",
        "3xl": "1.875rem",
        "4xl": "2.25rem",
        "base": "1rem",
        "scale": 1
      },
      "fontFamily": {
        "mono": "'Fira Code', 'Courier New', monospace",
        "primary": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "secondary": "Georgia, serif"
      },
      "fontWeight": {
        "bold": 700,
        "light": 300,
        "medium": 500,
        "normal": 400,
        "semibold": 600
      },
      "lineHeight": {
        "tight": 1.25,
        "normal": 1.5,
        "relaxed": 1.75
      }
    },
    "customizations": {
      "shadows": {
        "enabled": True,
        "intensity": "medium"
      },
      "animations": {
        "easing": "cubic-bezier(0.4, 0, 0.2, 1)",
        "enabled": True,
        "duration": "200ms"
      },
      "borderRadius": {
        "lg": "12px",
        "md": "8px",
        "sm": "4px",
        "full": "9999px"
      }
    }
  }
}

def flatten_colors(colors_dict, parent_key=''):
    items = []
    for k, v in colors_dict.items():
        new_key = f"{parent_key}-{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_colors(v, new_key).items())
        else:
            items.append((new_key, v))
    return dict(items)

def create_blocks(mode_data):
    blocks = {}
    colors = mode_data.get('colors', {})
    typography = mode_data.get('typography', {})
    
    # 1. Legacy Color Support (Block "color" -> --color-*)
    blocks["color"] = flatten_colors(colors)
    
    # 2. Legacy Font Support (Block "font" -> --font-*)
    font_family = typography.get('fontFamily', {})
    font_block = {}
    for k, v in font_family.items():
        font_block[k] = v
    # Handle scale
    font_scale = typography.get('fontSize', {}).get('scale', 1)
    font_block["scale"] = str(font_scale)
    blocks["font"] = font_block
    
    # 3. Component Blocks (Semantic Mapping)
    
    # Helper to safe get color (dot notation access logic simulation)
    def get_col(path):
        current = colors
        parts = path.split('.')
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return "#ff0000" # Error color
        return current

    # BLOCK: Header
    blocks["block_header_std"] = {
        "bg_color": get_col("action_bar_bg") if "action_bar_bg" in colors else get_col("background.primary"), # Fallback or specific logic
        "text_color": get_col("text.primary"),
        "border_bottom": f"1px solid {get_col('border.light')}",
        "shadow": "0 1px 2px 0 rgba(0, 0, 0, 0.05)"
    }
    
    # Correction for Header: In V2 Header logic, use background.primary as default
    blocks["block_header_std"]["bg_color"] = get_col("background.primary")
    
    # BLOCK: Input
    blocks["block_input_std"] = {
        "bg_color": get_col("background.primary"),
        "border": f"1px solid {get_col('border.medium')}",
        "text_color": get_col("text.primary"),
        "radius": "0.375rem"
    }
    
    # BLOCK: Buttons
    blocks["block_btn_primary"] = {
        "bg_color": get_col("primary.500"),
        "text_color": get_col("text.inverse"), # Usually inverse for primary btn
        "radius": "0.5rem",
        "hover_bg": get_col("primary.600")
    }
    
    # BLOCK: Surface Main
    blocks["block_surface_main"] = {
        "bg_color": get_col("background.primary"),
        "text_color": get_col("text.primary")
    }

    # BLOCK: Sidebar (Secondary BG)
    blocks["block_sidebar_std"] = {
        "bg_color": get_col("background.secondary"),
        "text_color": get_col("text.primary"), # Or secondary
        "border_right": f"1px solid {get_col('border.light')}"
    }

    return blocks

# Extract theme name and construct keys dynamically
theme_name = v1_data["ROOT"]["bezeichnung"].split()[0] # "Green"

v2_data = {
    f"{theme_name}_Light": create_blocks(v1_data["light"]),
    f"{theme_name}_Dark": create_blocks(v1_data["dark"]),
    "info": {
        "name": v1_data["ROOT"]["bezeichnung"],
        "description": v1_data["ROOT"]["description"],
        "created": v1_data["ROOT"]["created"],
        "version": "2.0 (Migrated)"
    }
}

print(json.dumps(v2_data, indent=2))
