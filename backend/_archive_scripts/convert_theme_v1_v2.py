import json

# Input JSON from user
v1_data = {
  "ROOT": {
    "created": "2026-01-05",
    "bezeichnung": "Orange Theme",
    "description": "Orange Theme color schema"
  },
  "dark": {
    "colors": {
      "info": "#42a5f5",
      "text": {
        "inverse": "#212121",
        "primary": "#ffffff",
        "disabled": "#6a6a6a",
        "secondary": "#b0b0b0",
        "on_primary": "#ffffff",
        "on_tertiary": "#111827",
        "on_secondary": "#e0e0e0"
      },
      "error": "#ef5350",
      "border": {
        "dark": "#5a4a3a",
        "light": "#3a2a1a",
        "medium": "#4a3a2a"
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
        "50": "#fff3e0",
        "100": "#ffe0b2",
        "200": "#ffcc80",
        "300": "#ffb74d",
        "400": "#ffa726",
        "500": "#ffb74d",
        "600": "#fb8c00",
        "700": "#f57c00",
        "800": "#ef6c00",
        "900": "#e65100"
      },
      "success": "#66bb6a",
      "warning": "#ffb74d",
      "secondary": {
        "50": "#e3f2fd",
        "100": "#bbdefb",
        "200": "#90caf9",
        "300": "#64b5f6",
        "400": "#42a5f5",
        "500": "#64b5f6",
        "600": "#1e88e5",
        "700": "#1976d2",
        "800": "#1565c0",
        "900": "#0d47a1"
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
        "enabled": true,
        "intensity": "medium"
      },
      "animations": {
        "easing": "cubic-bezier(0.4, 0, 0.2, 1)",
        "enabled": true,
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
        "primary": "#e65100",
        "disabled": "#bdbdbd",
        "secondary": "#616161",
        "on_primary": "#e65100",
        "on_tertiary": "#333333",
        "on_secondary": "#ffcc80"
      },
      "error": "#f44336",
      "border": {
        "dark": "#ffb74d",
        "light": "#ffe0b2",
        "medium": "#ffcc80"
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
        "50": "#fff3e0",
        "100": "#ffe0b2",
        "200": "#ffcc80",
        "300": "#ffb74d",
        "400": "#ffa726",
        "500": "#ff9800",
        "600": "#fb8c00",
        "700": "#f57c00",
        "800": "#ef6c00",
        "900": "#e65100"
      },
      "success": "#4caf50",
      "warning": "#ff9800",
      "secondary": {
        "50": "#e3f2fd",
        "100": "#bbdefb",
        "200": "#90caf9",
        "300": "#64b5f6",
        "400": "#42a5f5",
        "500": "#2196f3",
        "600": "#1e88e5",
        "700": "#1976d2",
        "800": "#1565c0",
        "900": "#0d47a1"
      },
      "background": {
        "primary": "#ffffff",
        "tertiary": "#fff3e0",
        "secondary": "#fff8f0"
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
        "enabled": true,
        "intensity": "medium"
      },
      "animations": {
        "easing": "cubic-bezier(0.4, 0, 0.2, 1)",
        "enabled": true,
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
        "bg_color": get_col("background.primary"),
        "text_color": get_col("text.primary"),
        "border_bottom": f"1px solid {get_col('border.light')}",
        "shadow": "0 1px 2px 0 rgba(0, 0, 0, 0.05)"
    }
    
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

# Generate V2 Structure
v2_data = {
    "Orange_Light": create_blocks(v1_data["light"]),
    "Orange_Dark": create_blocks(v1_data["dark"]),
    "info": {
        "name": v1_data["ROOT"]["bezeichnung"],
        "description": v1_data["ROOT"]["description"],
        "created": v1_data["ROOT"]["created"],
        "version": "2.0 (Migrated)"
    }
}

print(json.dumps(v2_data, indent=2))
