#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
This is a web service to print labels on Brother QL label printers.
"""

import argparse
import json
import logging
import random
import sys
from io import BytesIO

from bottle import get, post, request, response, route, run, static_file
from bottle import jinja2_view as view
from brother_ql import BrotherQLRaster, create_label
from brother_ql.backends import backend_factory, guess_backend
from brother_ql.devicedependent import (
    DIE_CUT_LABEL,
    ENDLESS_LABEL,
    ROUND_DIE_CUT_LABEL,
    label_sizes,
    label_type_specs,
    models,
)
from PIL import Image, ImageDraw, ImageFont

from font_helpers import get_fonts

logger = logging.getLogger(__name__)

LABEL_SIZES = [(name, label_type_specs[name]["name"]) for name in label_sizes]

try:
    with open("config.json", encoding="utf-8") as fh:
        CONFIG = json.load(fh)
except FileNotFoundError:
    with open("config.example.json", encoding="utf-8") as fh:
        CONFIG = json.load(fh)


@route("/")
@view("labeldesigner.jinja2")
def index():
    font_family_names = sorted(list(FONTS.keys()))
    printers = CONFIG.get("PRINTERS", [])
    default_printer = CONFIG.get("DEFAULT_PRINTER", 0)

    # If no printers defined, create one from legacy config
    if not printers:
        printers = [
            {
                "NAME": "Default Printer",
                "MODEL": CONFIG["PRINTER"]["MODEL"],
                "PRINTER": CONFIG["PRINTER"]["PRINTER"],
                "DEFAULT_LABEL": CONFIG["LABEL"]["DEFAULT_SIZE"],
            }
        ]
        default_printer = 0

    return {
        "font_family_names": font_family_names,
        "fonts": FONTS,
        "label_sizes": LABEL_SIZES,
        "printers": printers,
        "default_printer": default_printer,
        "website": CONFIG["WEBSITE"],
        "label": CONFIG["LABEL"],
    }


@route("/static/<filename:path>")
def serve_static(filename):
    return static_file(filename, root="./static")


def get_label_context(request):
    """might raise LookupError()"""

    d = request.params.decode()  # UTF-8 decoded form data

    font_family = d.get("font_family").rpartition("(")[0].strip()
    font_style = d.get("font_family").rpartition("(")[2].rstrip(")")
    context = {
        "text": d.get("text", None),
        "font_size": int(d.get("font_size", 100)),
        "font_family": font_family,
        "font_style": font_style,
        "label_size": d.get("label_size", "62"),
        "kind": label_type_specs[d.get("label_size", "62")]["kind"],
        "margin": int(d.get("margin", 10)),
        "threshold": int(d.get("threshold", 70)),
        "align": d.get("align", "center"),
        "orientation": d.get("orientation", "standard"),
        "margin_top": float(d.get("margin_top", 24)) / 100.0,
        "margin_bottom": float(d.get("margin_bottom", 45)) / 100.0,
        "margin_left": float(d.get("margin_left", 35)) / 100.0,
        "margin_right": float(d.get("margin_right", 35)) / 100.0,
    }
    context["margin_top"] = int(context["font_size"] * context["margin_top"])
    context["margin_bottom"] = int(context["font_size"] * context["margin_bottom"])
    context["margin_left"] = int(context["font_size"] * context["margin_left"])
    context["margin_right"] = int(context["font_size"] * context["margin_right"])

    context["fill_color"] = (255, 0, 0) if "red" in context["label_size"] else (0, 0, 0)

    def get_font_path(font_family_name, font_style_name):
        try:
            if font_family_name is None or font_style_name is None:
                font_family_name = CONFIG["LABEL"]["DEFAULT_FONTS"]["family"]
                font_style_name = CONFIG["LABEL"]["DEFAULT_FONTS"]["style"]
            font_path = FONTS[font_family_name][font_style_name]
        except KeyError:
            raise LookupError("Couln't find the font & style")
        return font_path

    context["font_path"] = get_font_path(context["font_family"], context["font_style"])

    def get_label_dimensions(label_size):
        try:
            ls = label_type_specs[context["label_size"]]
        except KeyError:
            raise LookupError("Unknown label_size")
        return ls["dots_printable"]

    width, height = get_label_dimensions(context["label_size"])
    if height > width:
        width, height = height, width
    if context["orientation"] == "rotated":
        height, width = width, height
    context["width"], context["height"] = width, height

    return context


def create_label_im(text, **kwargs):
    label_type = kwargs["kind"]
    im_font = ImageFont.truetype(kwargs["font_path"], kwargs["font_size"])
    im = Image.new("L", (20, 20), "white")
    draw = ImageDraw.Draw(im)

    # workaround for a bug in multiline_textsize()
    # when there are empty lines in the text:
    lines = []
    for line in text.split("\n"):
        if line == "":
            line = " "
        lines.append(line)
    text = "\n".join(lines)

    # Replace getsize with getbbox for text dimensions
    bbox = im_font.getbbox(text)
    textsize = draw.multiline_textbbox((0, 0), text, font=im_font)

    width, height = kwargs["width"], kwargs["height"]
    if kwargs["orientation"] == "standard":
        if label_type in (ENDLESS_LABEL,):
            height = textsize[3] + kwargs["margin_top"] + kwargs["margin_bottom"]
    elif kwargs["orientation"] == "rotated":
        if label_type in (ENDLESS_LABEL,):
            width = textsize[2] + kwargs["margin_left"] + kwargs["margin_right"]

    im = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(im)

    if kwargs["orientation"] == "standard":
        if label_type in (DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL):
            vertical_offset = (height - (textsize[3] - textsize[1])) // 2
            vertical_offset += (kwargs["margin_top"] - kwargs["margin_bottom"]) // 2
        else:
            vertical_offset = kwargs["margin_top"]
        horizontal_offset = max((width - (textsize[2] - textsize[0])) // 2, 0)
    elif kwargs["orientation"] == "rotated":
        vertical_offset = (height - (textsize[3] - textsize[1])) // 2
        vertical_offset += (kwargs["margin_top"] - kwargs["margin_bottom"]) // 2
        if label_type in (DIE_CUT_LABEL, ROUND_DIE_CUT_LABEL):
            horizontal_offset = max((width - (textsize[2] - textsize[0])) // 2, 0)
        else:
            horizontal_offset = kwargs["margin_left"]

    offset = horizontal_offset, vertical_offset
    draw.multiline_text(
        offset, text, kwargs["fill_color"], font=im_font, align=kwargs["align"]
    )
    return im


@get("/api/preview/text")
@post("/api/preview/text")
def get_preview_image():
    context = get_label_context(request)
    im = create_label_im(**context)
    return_format = request.query.get("return_format", "png")
    if return_format == "base64":
        import base64

        response.set_header("Content-type", "text/plain")
        return base64.b64encode(image_to_png_bytes(im))
    else:
        response.set_header("Content-type", "image/png")
        return image_to_png_bytes(im)


def image_to_png_bytes(im):
    image_buffer = BytesIO()
    im.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    return image_buffer.read()


@post("/api/print/text")
@get("/api/print/text")
def print_text():
    """
    API to print a label
    returns: JSON
    """
    return_dict = {"success": False}

    try:
        context = get_label_context(request)
    except LookupError as e:
        return_dict["error"] = e.msg
        return return_dict

    if context["text"] is None:
        return_dict["error"] = "Please provide the text for the label"
        return return_dict

    # Get selected printer
    printer_index = int(request.forms.get("printer", CONFIG.get("DEFAULT_PRINTER", 0)))
    printers = CONFIG.get("PRINTERS", [])

    if not printers:
        # Legacy config support
        selected_printer = {
            "MODEL": CONFIG["PRINTER"]["MODEL"],
            "PRINTER": CONFIG["PRINTER"]["PRINTER"],
        }
    else:
        selected_printer = printers[printer_index]

    im = create_label_im(**context)
    if DEBUG:
        im.save("sample-out.png")

    if context["kind"] == ENDLESS_LABEL:
        rotate = 0 if context["orientation"] == "standard" else 90
    elif context["kind"] in (ROUND_DIE_CUT_LABEL, DIE_CUT_LABEL):
        rotate = "auto"

    qlr = BrotherQLRaster(selected_printer["MODEL"])
    red = False
    if "red" in context["label_size"]:
        red = True
    create_label(
        qlr,
        im,
        context["label_size"],
        red=red,
        threshold=context["threshold"],
        cut=request.forms.get("cut", "true").lower() == "true",
        rotate=rotate,
    )

    if not DEBUG:
        try:
            be = BACKEND_CLASS(selected_printer["PRINTER"])
            be.write(qlr.data)
            be.dispose()
            del be
        except Exception as e:
            return_dict["message"] = str(e)
            logger.warning("Exception happened: %s", e)
            return return_dict

    return_dict["success"] = True
    if DEBUG:
        return_dict["data"] = str(qlr.data)
    return return_dict


@post("/print")
def print_label():
    """Print a label from the web interface."""

    # Get the selected printer from the form data
    printer_index = int(request.forms.get("printer", CONFIG.get("DEFAULT_PRINTER", 0)))
    printers = CONFIG.get("PRINTERS", [])

    if not printers:
        # Legacy config support
        selected_printer = {
            "MODEL": CONFIG["PRINTER"]["MODEL"],
            "PRINTER": CONFIG["PRINTER"]["PRINTER"],
        }
    else:
        selected_printer = printers[printer_index]

    # ... rest of your print logic, using selected_printer['MODEL'] and selected_printer['PRINTER'] ...


def main():
    global DEBUG, FONTS, BACKEND_CLASS, CONFIG
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=False)
    parser.add_argument(
        "--loglevel", type=lambda x: getattr(logging, x.upper()), default=False
    )
    parser.add_argument(
        "--font-folder", default=False, help="folder for additional .ttf/.otf fonts"
    )
    parser.add_argument(
        "--default-label-size",
        default=False,
        help="Label size inserted in your printer. Defaults to 62.",
    )
    parser.add_argument(
        "--default-orientation",
        default=False,
        choices=("standard", "rotated"),
        help='Label orientation, defaults to "standard". To turn your text by 90°, state "rotated".',
    )
    parser.add_argument(
        "--model",
        default=False,
        choices=models,
        help="The model of your printer (default: QL-500)",
    )
    parser.add_argument(
        "printer",
        nargs="?",
        default=False,
        help="String descriptor for the printer to use (like tcp://192.168.0.23:9100 or file:///dev/usb/lp0)",
    )
    args = parser.parse_args()

    # Handle command line printer configuration
    if args.printer:
        if not CONFIG.get("PRINTERS"):
            CONFIG["PRINTERS"] = [
                {
                    "NAME": "Default Printer",
                    "MODEL": CONFIG.get("PRINTER", {}).get("MODEL", "QL-500"),
                    "PRINTER": args.printer,
                    "DEFAULT_LABEL": CONFIG.get("LABEL", {}).get("DEFAULT_SIZE", "62"),
                }
            ]
            CONFIG["DEFAULT_PRINTER"] = 0

    if args.port:
        PORT = args.port
    else:
        PORT = CONFIG["SERVER"]["PORT"]

    if args.loglevel:
        LOGLEVEL = args.loglevel
    else:
        LOGLEVEL = CONFIG["SERVER"]["LOGLEVEL"]

    if LOGLEVEL == "DEBUG":
        DEBUG = True
    else:
        DEBUG = False

    if args.model:
        if CONFIG.get("PRINTERS"):
            CONFIG["PRINTERS"][CONFIG["DEFAULT_PRINTER"]]["MODEL"] = args.model
        else:
            CONFIG["PRINTER"] = CONFIG.get("PRINTER", {})
            CONFIG["PRINTER"]["MODEL"] = args.model

    if args.default_label_size:
        if CONFIG.get("PRINTERS"):
            CONFIG["PRINTERS"][CONFIG["DEFAULT_PRINTER"]]["DEFAULT_LABEL"] = (
                args.default_label_size
            )
        else:
            CONFIG["LABEL"]["DEFAULT_SIZE"] = args.default_label_size

    if args.default_orientation:
        CONFIG["LABEL"]["DEFAULT_ORIENTATION"] = args.default_orientation

    if args.font_folder:
        ADDITIONAL_FONT_FOLDER = args.font_folder
    else:
        ADDITIONAL_FONT_FOLDER = CONFIG["SERVER"]["ADDITIONAL_FONT_FOLDER"]

    logging.basicConfig(level=LOGLEVEL)

    # Get the default printer configuration
    if CONFIG.get("PRINTERS"):
        default_printer = CONFIG["PRINTERS"][CONFIG["DEFAULT_PRINTER"]]
        printer_string = default_printer["PRINTER"]
    else:
        printer_string = CONFIG["PRINTER"]["PRINTER"]

    try:
        selected_backend = guess_backend(printer_string)
    except ValueError:
        parser.error(
            "Couldn't guess the backend to use from the printer string descriptor"
        )
    BACKEND_CLASS = backend_factory(selected_backend)["backend_class"]

    if CONFIG.get("PRINTERS"):
        default_size = CONFIG["PRINTERS"][CONFIG["DEFAULT_PRINTER"]]["DEFAULT_LABEL"]
    else:
        default_size = CONFIG["LABEL"]["DEFAULT_SIZE"]

    if default_size not in label_sizes:
        parser.error(
            "Invalid default label size. Please choose one of the following:\n"
            + " ".join(label_sizes)
        )

    FONTS = get_fonts()
    if ADDITIONAL_FONT_FOLDER:
        FONTS.update(get_fonts(ADDITIONAL_FONT_FOLDER))

    if not FONTS:
        sys.stderr.write(
            'Not a single font was found on your system. Please install some or use the "--font-folder" argument.\n'
        )
        sys.exit(2)

    for font in CONFIG["LABEL"]["DEFAULT_FONTS"]:
        try:
            FONTS[font["family"]][font["style"]]
            CONFIG["LABEL"]["DEFAULT_FONTS"] = font
            logger.debug("Selected the following default font: {}".format(font))
            break
        except:
            pass
    if CONFIG["LABEL"]["DEFAULT_FONTS"] is None:
        sys.stderr.write(
            "Could not find any of the default fonts. Choosing a random one.\n"
        )
        family = random.choice(list(FONTS.keys()))
        style = random.choice(list(FONTS[family].keys()))
        CONFIG["LABEL"]["DEFAULT_FONTS"] = {"family": family, "style": style}
        sys.stderr.write(
            "The default font is now set to: {family} ({style})\n".format(
                **CONFIG["LABEL"]["DEFAULT_FONTS"]
            )
        )

    run(host=CONFIG["SERVER"]["HOST"], port=PORT, debug=DEBUG)


if __name__ == "__main__":
    main()
