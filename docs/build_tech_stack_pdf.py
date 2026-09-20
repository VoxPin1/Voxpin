#!/usr/bin/env python3
"""Build the VoxPin tech stack learning PDF."""

from __future__ import annotations

import os

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(DIR, "voxpin-tech-stack.pdf")
STATIC_OUT = os.path.join(DIR, "..", "backend", "voice_notes", "static", "voxpin-tech-stack.pdf")

PURPLE = HexColor("#6e56f5")
PURPLE_DEEP = HexColor("#5a45e8")
INK = HexColor("#16141f")
MIST = HexColor("#5a5470")
PAPER = HexColor("#f7f5ff")
GOLD = HexColor("#f4b133")

FONT_DIR = "/System/Library/Fonts/Supplemental"
pdfmetrics.registerFont(TTFont("VoxBody", os.path.join(FONT_DIR, "Arial.ttf")))
pdfmetrics.registerFont(TTFont("VoxBold", os.path.join(FONT_DIR, "Arial Bold.ttf")))


def styles():
    base = getSampleStyleSheet()
    return {
        "cover_kicker": ParagraphStyle(
            "cover_kicker",
            parent=base["Normal"],
            fontName="VoxBold",
            fontSize=11,
            textColor=PURPLE,
            alignment=TA_CENTER,
            letterSpacing=2,
            spaceAfter=8,
        ),
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Normal"],
            fontName="VoxBold",
            fontSize=32,
            leading=38,
            textColor=INK,
            alignment=TA_CENTER,
            spaceAfter=10,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="VoxBody",
            fontSize=13,
            leading=18,
            textColor=MIST,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Normal"],
            fontName="VoxBold",
            fontSize=18,
            leading=22,
            textColor=INK,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Normal"],
            fontName="VoxBold",
            fontSize=13,
            leading=17,
            textColor=PURPLE_DEEP,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="VoxBody",
            fontSize=11,
            leading=16,
            textColor=INK,
            spaceAfter=8,
        ),
        "step": ParagraphStyle(
            "step",
            parent=base["Normal"],
            fontName="VoxBody",
            fontSize=11,
            leading=15,
            textColor=INK,
            leftIndent=4,
        ),
        "step_title": ParagraphStyle(
            "step_title",
            parent=base["Normal"],
            fontName="VoxBold",
            fontSize=11,
            leading=15,
            textColor=INK,
        ),
        "caption": ParagraphStyle(
            "caption",
            parent=base["Normal"],
            fontName="VoxBody",
            fontSize=9,
            leading=12,
            textColor=MIST,
            alignment=TA_CENTER,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="VoxBody",
            fontSize=8,
            textColor=MIST,
            alignment=TA_CENTER,
        ),
        "cell_title": ParagraphStyle(
            "cell_title",
            parent=base["Normal"],
            fontName="VoxBold",
            fontSize=11,
            leading=14,
            textColor=INK,
        ),
        "cell_body": ParagraphStyle(
            "cell_body",
            parent=base["Normal"],
            fontName="VoxBody",
            fontSize=9.5,
            leading=13,
            textColor=MIST,
        ),
    }


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAPER)
    canvas.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
    canvas.setFillColor(PURPLE)
    canvas.rect(0, letter[1] - 18, letter[0], 18, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("VoxBold", 8)
    canvas.drawString(0.7 * inch, letter[1] - 12, "VoxPin  ·  Tech stack learning guide")
    canvas.drawRightString(letter[0] - 0.7 * inch, letter[1] - 12, "Think it. Jot it. Do it.")
    canvas.setFillColor(PURPLE)
    canvas.rect(0, 0, letter[0], 28, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("VoxBody", 8)
    canvas.drawString(0.7 * inch, 12, "Waveshare ESP32 S3 LCD pin  ·  Mac helper  ·  Google")
    canvas.drawRightString(letter[0] - 0.7 * inch, 12, f"Page {doc.page}")
    canvas.restoreState()


def cover_page(canvas, doc):
    header_footer(canvas, doc)
    canvas.saveState()
    canvas.setFillColor(PURPLE)
    canvas.circle(1.15 * inch, letter[1] - 1.55 * inch, 18, fill=1, stroke=0)
    canvas.setFillColor(GOLD)
    canvas.circle(1.15 * inch, letter[1] - 1.55 * inch, 7, fill=1, stroke=0)
    canvas.restoreState()


def card_table(s, rows):
    data = []
    for title, body in rows:
        data.append(
            [
                Paragraph(title, s["cell_title"]),
                Paragraph(body, s["cell_body"]),
            ]
        )
    table = Table(data, colWidths=[1.8 * inch, 5.0 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), white),
                ("BOX", (0, 0), (-1, -1), 0.6, HexColor("#d9d3ff")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, HexColor("#ece8ff")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def steps(s, items):
    flow = []
    for i, (title, body) in enumerate(items, 1):
        flow.append(
            Paragraph(f"<b>{i}. {title}</b>  {body}", s["step"])
        )
    return flow


def build():
    s = styles()
    doc = SimpleDocTemplate(
        OUT,
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title="VoxPin Tech Stack Learning Guide",
        author="VoxPin",
    )
    story = []

    story.append(Spacer(1, 1.35 * inch))
    story.append(Paragraph("LEARNING GUIDE", s["cover_kicker"]))
    story.append(Paragraph("How VoxPin works", s["cover_title"]))
    story.append(
        Paragraph(
            "A simple guide to the whole tech stack, with every step named.",
            s["cover_sub"],
        )
    )
    story.append(
        Paragraph(
            "The pin is a <b>Waveshare ESP32 S3 LCD</b> board. A Python helper on the Mac "
            "does the thinking. Google keeps notes and reminders.",
            s["cover_sub"],
        )
    )
    story.append(Spacer(1, 0.35 * inch))
    story.append(
        Paragraph(
            "Made for people learning the project. Read it in order, then try each job on the pin.",
            s["caption"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("1. The big picture", s["h1"]))
    story.append(
        Paragraph(
            "VoxPin is not one computer. It is three parts that talk to each other.",
            s["body"],
        )
    )
    story.append(
        card_table(
            s,
            [
                (
                    "Waveshare pin",
                    "The board you hold. Waveshare makes this hardware. The chip is ESP32 S3. "
                    "It has a tiny color screen, a mic, a speaker, a battery, and buttons.",
                ),
                (
                    "Mac helper",
                    "A Python Flask program on the laptop. It listens on port 8765. "
                    "It turns speech into words, then saves a note, sets a reminder, translates, or sends SOS.",
                ),
                (
                    "Google and GitHub",
                    "Google Calendar stores reminders. A Google Doc stores notes. "
                    "GitHub Pages hosts the public website.",
                ),
            ],
        )
    )
    story.append(Spacer(1, 0.16 * inch))
    story.append(
        Paragraph(
            "The pin is the walkie talkie. The Mac is the brain. Google is the notebook. "
            "The pin does not log into Google by itself.",
            s["body"],
        )
    )

    story.append(Paragraph("2. Inside the Waveshare board", s["h1"]))
    story.append(
        Paragraph(
            "Board name: Waveshare ESP32 S3 LCD 0.85. The screen is 128 by 128 pixels. "
            "WiFi is 2.4 GHz only.",
            s["body"],
        )
    )
    story.append(
        card_table(
            s,
            [
                ("ESP32 S3 chip", "The brain on the board. It runs the C++ program we flash onto the pin."),
                ("Color LCD", "Shows time, battery, and the next reminder, like Violin practice at 4."),
                ("Mic and speaker", "Mic records when you hold to talk. Speaker plays answers and reminder buzzes."),
                ("Buttons", "Hold to talk records your voice. PLUS sends SOS to a parent."),
                ("WiFi radio", "Sends audio to the Mac on the same network. Also finds the helper with a beacon."),
                ("Bluetooth", "Lets a phone or laptop set a name and language on the pin."),
            ],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("3. Hold to talk, step by step", s["h1"]))
    story.append(
        Paragraph(
            "This is the main path. Every voice job starts here.",
            s["body"],
        )
    )
    story.extend(
        steps(
            s,
            [
                (
                    "You hold the Waveshare pin.",
                    "The C++ program sees the button and starts the mic.",
                ),
                (
                    "The pin records sound.",
                    "It stores audio in memory as PCM. It does not keep a sound file after the job is done.",
                ),
                (
                    "WiFi carries the clip.",
                    "The pin POSTs the recording to the Mac helper, usually http://the-mac-ip:8765/note.",
                ),
                (
                    "The helper turns speech into words.",
                    "Python sends the clip to speech recognition and gets a transcript, like set a reminder at 4.",
                ),
                (
                    "The helper picks the job.",
                    "A sorter looks at the words: note, remind, translate, SOS, weather, or ask.",
                ),
                (
                    "Google or iMessage does the save.",
                    "Notes go in a Doc. Reminders go on Calendar. SOS texts a parent.",
                ),
                (
                    "The pin talks back.",
                    "The helper makes spoken audio and sends it. The Waveshare speaker plays it.",
                ),
            ],
        )
    )

    story.append(Paragraph("4. What happens after the words are read", s["h1"]))
    story.append(Paragraph("Notes", s["h2"]))
    story.append(
        Paragraph(
            "If you say take notes, the helper writes the words to the Google Doc. "
            "The pin can say Notes added. The sound itself is not saved.",
            s["body"],
        )
    )
    story.append(Paragraph("Reminders", s["h2"]))
    story.append(
        Paragraph(
            "If you say set a reminder, the helper reads the time and the length. "
            "At 4 tomorrow for 1 hour starts at 4 and lasts 1 hour. "
            "1 hour and 30 min lasts 90 minutes, not 10 minutes and not a default 15 minute block.",
            s["body"],
        )
    )
    story.append(Paragraph("Translate", s["h2"]))
    story.append(
        Paragraph(
            "If you say translate, the helper changes the phrase into the language you picked "
            "and sends speech back to the pin.",
            s["body"],
        )
    )

    story.append(PageBreak())
    story.append(Paragraph("5. Reminder buzz, step by step", s["h1"]))
    story.append(
        Paragraph(
            "The pin can warn you about 10 minutes before a timed reminder. "
            "That 10 minutes is the warning, not the event length.",
            s["body"],
        )
    )
    story.extend(
        steps(
            s,
            [
                (
                    "Calendar already has the event.",
                    "You set it by voice, with the start time and how long it lasts.",
                ),
                (
                    "The helper watches the clock.",
                    "The pin asks /reminder-due. The helper checks Google Calendar.",
                ),
                (
                    "When it is 0 to 10 minutes away, due is true.",
                    "All day events do not buzz. The same event is not announced twice.",
                ),
                (
                    "The Waveshare pin wakes.",
                    "If it was sleeping, it wakes so you can hear it.",
                ),
                (
                    "The speaker buzzes.",
                    "Three pulses play. This board has no extra buzzer chip, so the speaker does the buzz.",
                ),
                (
                    "The pin speaks the reminder.",
                    "It asks /announce-reminder and plays speech like Reminder. Violin practice at 4:00 PM.",
                ),
            ],
        )
    )

    story.append(Paragraph("6. SOS, step by step", s["h1"]))
    story.extend(
        steps(
            s,
            [
                (
                    "You press PLUS on the Waveshare pin.",
                    "The pin does not text by itself. It only asks the helper.",
                ),
                (
                    "The pin POSTs /sos.",
                    "It can include nearby WiFi clues so the helper can guess a place.",
                ),
                (
                    "The Mac sends iMessage.",
                    "A parent gets a pickup message and a location if the helper can find one.",
                ),
                (
                    "The pin shows a short status.",
                    "Then it goes quiet again.",
                ),
            ],
        )
    )

    story.append(Paragraph("7. The website", s["h1"]))
    story.append(
        Paragraph(
            "The public site is HTML on GitHub Pages. The same pages also run on the Mac helper. "
            "The How it works section is the short version of this guide. "
            "This PDF is the longer version you can print and hand out.",
            s["body"],
        )
    )
    story.append(Paragraph("Words to know", s["h2"]))
    story.append(
        card_table(
            s,
            [
                ("Waveshare", "The company that makes the pin board we flash."),
                ("ESP32 S3", "The chip on that board. It can do WiFi and Bluetooth."),
                ("Firmware", "The C++ program that lives on the pin after we flash it."),
                ("Helper", "The Python Flask app on the Mac that reads speech and talks to Google."),
                ("Beacon", "A short WiFi shout so the pin can find the Mac IP address."),
            ],
        )
    )
    story.append(Spacer(1, 0.2 * inch))
    story.append(
        Paragraph(
            "Practice prompt: say a reminder at a real time, with a length like 1 hour, "
            "then watch Calendar. About 10 minutes before, the Waveshare pin should buzz and speak.",
            s["body"],
        )
    )

    def first_page(canvas, doc):
        cover_page(canvas, doc)

    doc.build(story, onFirstPage=first_page, onLaterPages=header_footer)
    static_dir = os.path.dirname(os.path.abspath(STATIC_OUT))
    if os.path.isdir(static_dir):
        import shutil

        shutil.copy2(OUT, STATIC_OUT)
    print(OUT)


if __name__ == "__main__":
    build()
