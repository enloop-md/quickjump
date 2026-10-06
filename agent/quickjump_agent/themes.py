"""
Colour schemes for the agent window.

A scheme has a dark and a light variant; which one is used follows the
desktop (or the user's choice). The user can override any colour of either
variant on top of the scheme.

Config shape (cfg['theme']):
    {'scheme': 'amber', 'mode': 'system' | 'dark' | 'light',
     'custom': {'dark': {key: '#rrggbb'}, 'light': {...}}}
"""

# key -> label, in the order the settings dialog shows them.
KEYS = {
    'bg': 'Background',
    'head': 'Header',
    'fg': 'Text',
    'muted': 'Secondary text',
    'accent': 'Accent (title, numbers)',
    'border': 'Border',
    'hover': 'Row under the mouse',
    'active': 'Selected chip, icon tiles',
    'line': 'Separators',
}

SCHEMES = {
    # The default: nothing like the grey/blue of other windows.
    'amber': {
        'name': 'Amber',
        'dark': dict(bg='#1f1a33', head='#2d2550', fg='#f4f1ff', muted='#b3aad6', hover='#3a3066',
                     active='#4a3d80', line='#3d3468', accent='#f5a524', border='#f5a524'),
        'light': dict(bg='#fff8ea', head='#ffe6b0', fg='#2b1f05', muted='#8a6a2f', hover='#ffefc9',
                      active='#ffe1a1', line='#f0d49a', accent='#c2410c', border='#e08a00'),
    },
    'ocean': {
        'name': 'Ocean',
        'dark': dict(bg='#0f2a33', head='#16404d', fg='#e8fbff', muted='#8fc3cf', hover='#1d5161',
                     active='#24657a', line='#22505e', accent='#2ee6c8', border='#2ee6c8'),
        'light': dict(bg='#ecfbfa', head='#c9f2ee', fg='#062a2f', muted='#3c7a80', hover='#dcf6f4',
                      active='#bfeee9', line='#a8e3dd', accent='#0f8f86', border='#14a39a'),
    },
    'forest': {
        'name': 'Forest',
        'dark': dict(bg='#13241a', head='#1d3a27', fg='#eefbea', muted='#9cc4a2', hover='#264d33',
                     active='#2f5f3f', line='#2a4a33', accent='#8bd450', border='#8bd450'),
        'light': dict(bg='#f1faea', head='#d8f0c4', fg='#132a0a', muted='#55783f', hover='#e4f5d6',
                      active='#cdeab4', line='#bfe0a3', accent='#3f7f10', border='#5a9e1a'),
    },
    'rose': {
        'name': 'Rose',
        'dark': dict(bg='#2a1520', head='#45203a', fg='#fff0f6', muted='#d6a3bf', hover='#55284a',
                     active='#66305a', line='#4d2643', accent='#ff5fa2', border='#ff5fa2'),
        'light': dict(bg='#fff1f6', head='#ffd6e7', fg='#3a0a20', muted='#9a4a6e', hover='#ffe4ef',
                      active='#ffc9de', line='#f5b6cf', accent='#c2185b', border='#e0447f'),
    },
    'classic': {
        'name': 'Classic (grey and blue)',
        'dark': dict(bg='#171a21', head='#1f232c', fg='#e6e8ee', muted='#8b93a7', hover='#262b36',
                     active='#2f3542', line='#2a2f3a', accent='#6aa8ff', border='#6aa8ff'),
        'light': dict(bg='#f7f8fa', head='#eef1f5', fg='#1b1f27', muted='#6b7280', hover='#e9ecf2',
                      active='#dde2ea', line='#dfe3ea', accent='#2563eb', border='#2563eb'),
    },
    'contrast': {
        'name': 'High contrast',
        'dark': dict(bg='#000000', head='#1a1a1a', fg='#ffffff', muted='#cccccc', hover='#333333',
                     active='#444444', line='#666666', accent='#ffff00', border='#ffff00'),
        'light': dict(bg='#ffffff', head='#e6e6e6', fg='#000000', muted='#333333', hover='#e0e0e0',
                      active='#cccccc', line='#888888', accent='#0000cc', border='#000000'),
    },
}

DEFAULT = {'scheme': 'amber', 'mode': 'system', 'custom': {'dark': {}, 'light': {}}}


def normalise(theme):
    theme = dict(DEFAULT, **(theme or {}))
    if theme['scheme'] not in SCHEMES:
        theme['scheme'] = DEFAULT['scheme']
    if theme['mode'] not in ('system', 'dark', 'light'):
        theme['mode'] = 'system'
    custom = theme.get('custom') or {}
    theme['custom'] = {v: {k: c for k, c in (custom.get(v) or {}).items() if k in KEYS}
                       for v in ('dark', 'light')}
    return theme


def variant(theme, system_dark):
    mode = normalise(theme)['mode']
    return mode if mode != 'system' else ('dark' if system_dark else 'light')


def resolve(theme, system_dark):
    """The colours to paint with."""
    theme = normalise(theme)
    v = variant(theme, system_dark)
    return {**SCHEMES[theme['scheme']][v], **theme['custom'][v]}
