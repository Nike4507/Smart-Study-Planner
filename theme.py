"""theme.py — all visual styling in one place (CSS, fonts, small HTML components).

Change the palette by editing the variables at the top of CSS. Fonts: Fraunces (headings,
numbers) + Manrope (everything else), loaded from Google Fonts with system fallbacks.
"""
from __future__ import annotations

import html

import streamlit as st

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Manrope:wght@400;500;600;700&display=swap');
:root{--bg:#101120;--surface:#191a2e;--surface2:#222440;--line:rgba(255,255,255,.07);--text:#eceaf4;--muted:#9a9bb5;
--coral:#ff7a6b;--rose:#ee5a91;--teal:#4fd1b0;--violet:#8b7cf6;--amber:#f5b94c;
--grad:linear-gradient(135deg,#ff8a6b 0%,#ee5a91 100%);--shadow:0 12px 32px rgba(0,0,0,.28);--shadow-lg:0 18px 40px rgba(0,0,0,.4)}
html,body,.stApp,p,label,li,input,textarea,button,select,td,th,[data-testid="stMarkdownContainer"],[data-testid="stCaptionContainer"]{font-family:'Manrope','Segoe UI',system-ui,sans-serif}
[data-testid="stIconMaterial"],.material-symbols-rounded{font-family:'Material Symbols Rounded'!important}
.stApp{background:var(--bg)}
[data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer{display:none!important}
header[data-testid="stHeader"]{background:transparent}
.block-container{max-width:1180px;padding:3.2rem 3.5rem 6rem}
[data-testid="stVerticalBlock"]{gap:1.4rem}
h1,h2,h3,h4{font-family:'Fraunces',Georgia,serif!important;font-weight:500!important;letter-spacing:-.01em;color:var(--text)}
h2{font-size:1.6rem!important;margin-top:1.2rem!important}h3{font-size:1.25rem!important}
.page-title{font-family:'Fraunces',Georgia,serif;font-size:2.6rem;font-weight:500;line-height:1.1;margin:0 0 .4rem;letter-spacing:-.02em}
.page-sub{color:var(--muted);font-size:1.02rem;margin:0 0 1.2rem;line-height:1.6;max-width:62ch}
.section-title{font-family:'Fraunces',Georgia,serif;font-size:1.45rem;font-weight:500;margin:1.2rem 0 .2rem}
/* sidebar */
[data-testid="stSidebar"]{background:linear-gradient(175deg,#ff8a6b 0%,#ee5a91 62%,#b84a9a 100%);border-right:0;box-shadow:8px 0 40px rgba(0,0,0,.35)}
[data-testid="stSidebar"] *{color:#fff}
[data-testid="stSidebarUserContent"]{padding:.4rem 1.2rem 2rem}
.brand{font-family:'Fraunces',Georgia,serif;font-size:2.35rem;font-weight:500;line-height:1.05;letter-spacing:-.02em;margin:.4rem 0 .5rem}
.brand-sub{font-size:.92rem;opacity:.85;margin-bottom:2rem}
[data-testid="stSidebar"] div[role="radiogroup"]{gap:.55rem}
[data-testid="stSidebar"] label[data-baseweb="radio"]{padding:.95rem 1.2rem;border-radius:16px;width:100%;margin:0;transition:all .18s ease;cursor:pointer}
[data-testid="stSidebar"] label[data-baseweb="radio"]>div:first-child{display:none}
[data-testid="stSidebar"] label[data-baseweb="radio"] p{font-size:1.08rem;font-weight:600;letter-spacing:.005em}
[data-testid="stSidebar"] label[data-baseweb="radio"]:hover{background:rgba(255,255,255,.14)}
[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked){background:rgba(255,255,255,.26);box-shadow:0 8px 22px rgba(80,10,60,.28)}
.side-stat{background:rgba(255,255,255,.16);border-radius:18px;padding:1rem 1.2rem;margin:1.8rem 0 1rem;line-height:1.7;font-size:.98rem}
.side-stat b{font-family:'Fraunces',serif;font-size:1.35rem;font-weight:500}
[data-testid="stSidebar"] [data-testid="stExpander"] details{background:rgba(255,255,255,.12);border:0;border-radius:16px}
[data-testid="stSidebar"] input{color:#222!important}
/* cards */
[class*="st-key-card_"]{background:var(--surface);border:1px solid var(--line);border-radius:22px;padding:1.6rem 1.8rem;box-shadow:var(--shadow)}
[class*="st-key-card_"] [data-testid="stVerticalBlock"]{gap:.9rem}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:22px;padding:1.4rem 1.6rem;box-shadow:var(--shadow);height:100%}
.stat-label{color:var(--muted);font-size:.92rem;font-weight:500}
.stat-value{font-family:'Fraunces',Georgia,serif;font-size:2.3rem;font-weight:500;line-height:1.2;margin:.35rem 0 .2rem}
.stat-sub{color:var(--muted);font-size:.86rem}
.muted{color:var(--muted)}
.row{display:flex;align-items:center;gap:1rem;padding:.95rem 0;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:0}.row .time{color:var(--muted);font-size:.9rem;min-width:7.2rem;font-variant-numeric:tabular-nums}
.row .title{font-weight:600;font-size:1.02rem}.row .meta{color:var(--muted);font-size:.86rem;margin-top:.15rem}.row .grow{flex:1}
.chip{display:inline-block;padding:.28rem .8rem;border-radius:99px;font-size:.78rem;font-weight:600}
.chip.done{background:rgba(79,209,176,.16);color:var(--teal)}.chip.pending{background:rgba(245,185,76,.15);color:var(--amber)}
.chip.missed{background:rgba(238,90,145,.16);color:var(--rose)}.chip.skipped{background:rgba(154,155,181,.16);color:var(--muted)}
.chip.info{background:rgba(139,124,246,.16);color:var(--violet)}
.badge{background:var(--surface);border:1px solid var(--line);border-radius:22px;padding:1.4rem;box-shadow:var(--shadow);height:100%}
.badge.locked{opacity:.5;box-shadow:none}.badge .mark{width:44px;height:44px;border-radius:14px;background:var(--grad);margin-bottom:.9rem}
.badge.locked .mark{background:var(--surface2)}.badge b{font-size:1.02rem}.badge p{color:var(--muted);font-size:.86rem;margin:.3rem 0 0}
/* buttons: raised, soft, lift on hover */
button[data-testid="stBaseButton-secondary"],button[data-testid="stBaseButton-secondaryFormSubmit"],button[data-testid="stBaseButton-tertiary"]{background:var(--surface2);border:1px solid var(--line);border-radius:14px;min-height:2.9rem;padding:.55rem 1.3rem;font-weight:600;box-shadow:0 6px 16px rgba(0,0,0,.3),inset 0 1px 0 rgba(255,255,255,.05);transition:transform .16s ease,box-shadow .16s ease}
button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primaryFormSubmit"]{background:var(--grad);border:0;color:#fff;border-radius:14px;min-height:2.9rem;padding:.55rem 1.4rem;font-weight:700;box-shadow:0 10px 24px rgba(238,90,145,.38);transition:transform .16s ease,box-shadow .16s ease}
button[data-testid^="stBaseButton"]:not(:disabled):hover{transform:translateY(-3px);box-shadow:var(--shadow-lg)}
button[data-testid="stBaseButton-primary"]:not(:disabled):hover{box-shadow:0 16px 32px rgba(238,90,145,.5)}
button[data-testid^="stBaseButton"]:not(:disabled):active{transform:translateY(0);box-shadow:0 3px 8px rgba(0,0,0,.3)}
button[data-testid^="stBaseButton"]:disabled{opacity:.45;box-shadow:none}
/* inputs */
div[data-baseweb="input"],div[data-baseweb="base-input"],div[data-baseweb="select"]>div,div[data-baseweb="textarea"],[data-testid="stDateInputField"]{border-radius:14px!important;border-color:var(--line)!important;background:var(--surface2)!important}
textarea,input{border-radius:14px!important}
[data-testid="stFileUploaderDropzone"]{border-radius:18px;border:1.5px dashed rgba(255,255,255,.16);background:var(--surface2);padding:1.4rem}
[data-testid="stExpander"] details{border:1px solid var(--line);border-radius:18px;background:var(--surface);box-shadow:var(--shadow)}
[data-testid="stExpander"] summary{padding:1rem 1.3rem;font-weight:600}
[data-testid="stAlert"]{border-radius:16px;border:0}
[data-testid="stProgress"] [role="progressbar"]{border-radius:99px;height:10px;background:var(--surface2)}
[data-testid="stProgress"] [role="progressbar"]>div{border-radius:99px;background:var(--grad)}
[data-testid="stDataFrame"]{border-radius:16px;overflow:hidden}
[data-testid="stButtonGroup"] button{border-radius:14px}
/* phone: top navigation bar */
.st-key-topnav{display:none}
[data-testid="stExpandSidebarButton"],[data-testid="stSidebarCollapsedControl"]{background:linear-gradient(135deg,#ff8a6b,#ee5a91);border-radius:14px;box-shadow:0 8px 20px rgba(238,90,145,.4);color:#fff}
[data-testid="stExpandSidebarButton"] *,[data-testid="stSidebarCollapsedControl"] *{color:#fff!important}
.topbrand{font-family:'Fraunces',Georgia,serif;font-size:1.7rem;font-weight:500;letter-spacing:-.02em;margin:0 0 .6rem}
@media(max-width:800px){.st-key-topnav{display:block;background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:1rem 1rem .8rem;box-shadow:var(--shadow)}
.st-key-topnav button{min-height:2.6rem;font-size:.95rem}}
/* focus timer */
.focus-wrap{min-height:72vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.focus-label{color:var(--muted);font-size:1.1rem;margin-bottom:1.6rem}
.focus-time{font-family:'Fraunces',Georgia,serif;font-size:4.2rem;font-weight:400;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
@media(max-width:800px){.block-container{padding:2rem 1.2rem 5rem}.page-title{font-size:2rem}}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

FOCUS_CSS = """.st-key-topnav{display:none!important}
[data-testid="stSidebar"], [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none!important}
.block-container{max-width:760px}"""


def inject(focus: bool = False) -> None:
    st.markdown(f"<style>{CSS}{FOCUS_CSS if focus else ''}</style>", unsafe_allow_html=True)
    st.session_state["_card_n"] = 0


def card():
    """A soft, raised card. Use as ``with card(): ...``."""
    n = st.session_state.get("_card_n", 0)
    st.session_state["_card_n"] = n + 1
    return st.container(key=f"card_{n}")


def esc(text) -> str:
    return html.escape(str(text))


def page_header(title: str, sub: str = "") -> None:
    st.markdown(f"<div class='page-title'>{esc(title)}</div>" + (f"<div class='page-sub'>{esc(sub)}</div>" if sub else ""),
                unsafe_allow_html=True)


def section(title: str, sub: str = "") -> None:
    st.markdown(f"<div class='section-title'>{esc(title)}</div>" + (f"<div class='page-sub'>{esc(sub)}</div>" if sub else ""),
                unsafe_allow_html=True)


def stat(label: str, value, sub: str = "") -> None:
    st.markdown(f"<div class='stat'><div class='stat-label'>{esc(label)}</div><div class='stat-value'>{esc(value)}</div>"
                f"<div class='stat-sub'>{esc(sub) or '&nbsp;'}</div></div>", unsafe_allow_html=True)


def chip(status: str) -> str:
    label = {"pending": "Upcoming", "done": "Done", "missed": "Missed", "skipped": "Skipped"}.get(status, status.title())
    return f"<span class='chip {esc(status)}'>{label}</span>"


def row(time_text: str, title: str, meta: str = "", status: str = "") -> str:
    return (f"<div class='row'><div class='time'>{esc(time_text)}</div><div class='grow'><div class='title'>{esc(title)}</div>"
            f"<div class='meta'>{esc(meta)}</div></div>{chip(status) if status else ''}</div>")


def badge(name: str, desc: str, earned: bool) -> None:
    st.markdown(f"<div class='badge {'' if earned else 'locked'}'><div class='mark'></div><b>{esc(name)}</b>"
                f"<p>{esc(desc)}</p><p>{'Earned' if earned else 'Locked'}</p></div>", unsafe_allow_html=True)


def ring_svg(fraction: float, size: int = 320, stroke: int = 14) -> str:
    r = (size - stroke) / 2
    c = 2 * 3.14159265 * r
    off = c * (1 - max(0.0, min(1.0, fraction)))
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 {size} {size}'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
            f"<stop offset='0' stop-color='#ff8a6b'/><stop offset='1' stop-color='#ee5a91'/></linearGradient></defs>"
            f"<circle cx='{size/2}' cy='{size/2}' r='{r}' fill='none' stroke='rgba(255,255,255,.08)' stroke-width='{stroke}'/>"
            f"<circle cx='{size/2}' cy='{size/2}' r='{r}' fill='none' stroke='url(#g)' stroke-width='{stroke}' stroke-linecap='round' "
            f"stroke-dasharray='{c:.1f}' stroke-dashoffset='{off:.1f}' transform='rotate(-90 {size/2} {size/2})'/></svg>")
