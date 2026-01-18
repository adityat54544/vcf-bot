import os
import re
import uuid
import time
import tempfile
import asyncio
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Document,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, NetworkError, BadRequest

from bot.config import settings

# ---------------- CONFIG ----------------

# Keep-alive configuration
KEEP_ALIVE_INTERVAL = 180  # 3 minutes in seconds
KEEP_ALIVE_ENABLED = True  # Enable keep-alive mechanism
KEEP_ALIVE_SILENT_MODE = True  # Completely silent - no Telegram messages sent

# Channel configuration - can be overridden via environment variables
def get_channel_config():
    channels_env = os.getenv("REQUIRED_CHANNELS")
    if channels_env:
        try:
            return json.loads(channels_env)
        except json.JSONDecodeError:
            logger.warning("Invalid REQUIRED_CHANNELS JSON, using default")

    return [
        {"username": "@aurabots0", "invite_url": "https://t.me/+_RfSmS5WOOM3MGRl"},
        {"username": "@workbyaditya", "invite_url": "https://t.me/workbyaditya"},
        {"username": "@aurachatsws", "invite_url": "https://t.me/aurachatsws"}
    ]

REQUIRED_CHANNELS = get_channel_config()
MAX_FILE_MB = 20
CREDIT = "Created by @adityat_5454"

BASE_TMP = Path(tempfile.gettempdir()) / "aura_vcf_bot"
BASE_TMP.mkdir(parents=True, exist_ok=True)

PHONE_REGEX = re.compile(r"\+?\d{7,15}")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aura_vcf_bot")

# ---------------- UTILITIES ----------------

async def check_channel_membership(bot, user_id, channel):
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def check_all_memberships(bot, user_id):
    """Check if user is a member of all required channels."""
    # Check all channels in parallel for better performance
    tasks = [check_channel_membership(bot, user_id, channel_info["username"]) for channel_info in REQUIRED_CHANNELS]
    results = await asyncio.gather(*tasks)
    return all(results)

def normalize_number(raw: str) -> str:
    return "+" + re.sub(r"\D+", "", (raw or ""))

def extract_numbers(text: str) -> List[str]:
    seen, out = set(), []
    for m in PHONE_REGEX.finditer(text):
        n = normalize_number(m.group())
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out

def parse_vcf(text: str) -> List[Dict[str, str]]:
    contacts = []
    for block in re.split(r"END:VCARD", text, flags=re.I):
        if "BEGIN:VCARD" not in block.upper():
            continue
        name = re.search(r"FN:(.+)", block, flags=re.I)
        tel = re.search(r"TEL[^:]*:(.+)", block, flags=re.I)
        if tel:
            contacts.append({
                "name": name.group(1).strip() if name else "Unknown",
                "phone": normalize_number(tel.group(1).strip())
            })
    return contacts

def build_vcf(contacts: List[Dict[str, str]]) -> str:
    lines = []
    for c in contacts:
        lines.extend([
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:{c['name']}",
            f"TEL:{c['phone']}",
            "END:VCARD",
        ])
    return "\n".join(lines) + "\n"

# ---------------- TEMP FILE MANAGEMENT ----------------

def track_temp_file(context, file_path: Path):
    """Track a temporary file for cleanup later."""
    if "temp_files" not in context.user_data:
        context.user_data["temp_files"] = []
    context.user_data["temp_files"].append(str(file_path))

async def cleanup_temp_files(context):
    """Clean up all tracked temporary files."""
    temp_files = context.user_data.get("temp_files", [])
    for file_path_str in temp_files:
        try:
            file_path = Path(file_path_str)
            if file_path.exists():
                file_path.unlink()
                logger.info("Cleaned up temp file: %s", file_path_str)
        except Exception as e:
            logger.warning("Failed to clean up temp file %s: %s", file_path_str, e)
    context.user_data["temp_files"] = []

# ---------------- STATE MANAGEMENT ----------------

def set_state(context, state: str, mode: Optional[str] = None):
    """Set the current state and optionally mode."""
    context.user_data["state"] = state
    if mode:
        context.user_data["mode"] = mode

def get_state(context) -> str:
    """Get the current state."""
    return context.user_data.get("state", "idle")

def is_awaiting_data(context) -> bool:
    """Check if the bot is awaiting data input."""
    return get_state(context) == "awaiting_data"

def is_awaiting_instruction(context) -> bool:
    """Check if the bot is awaiting instruction input."""
    return get_state(context) == "awaiting_instruction"

def is_awaiting_files(context) -> bool:
    """Check if the bot is awaiting file uploads."""
    return get_state(context) == "awaiting_files"

def validate_positive_integer(value: str) -> Optional[int]:
    """Validate and convert string to positive integer."""
    try:
        num = int(value)
        return num if num > 0 else None
    except ValueError:
        return None

# ---------------- ASYNC FILE I/O ----------------

def _sync_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def _sync_write_text(path: Path, data: str) -> None:
    path.write_text(data, encoding="utf-8")

def _sync_copy_file(src: Path, dst: Path) -> None:
    dst.write_bytes(src.read_bytes())

async def _save_doc_to_tmp(doc: Document) -> Tuple[Path, str]:
    file_id = str(uuid.uuid4())[:8]
    original_name = doc.file_name or f"file_{file_id}"
    target = BASE_TMP / f"{file_id}_{original_name}"
    tf = await doc.get_file()
    await tf.download_to_drive(custom_path=str(target))
    return target, original_name

async def safe_send(chat, path: Path, filename: str, retries: int = 2) -> bool:
    attempt = 0
    while attempt <= retries:
        try:
            with path.open("rb") as fh:
                await chat.send_document(document=fh, filename=filename)
            await asyncio.sleep(0.05)
            return True
        except (TimedOut, NetworkError) as e:
            attempt += 1
            logger.warning("Transient send error (attempt %d) for %s: %s", attempt, filename, e)
            await asyncio.sleep(0.5 * attempt)
        except BadRequest as e:
            logger.exception("BadRequest sending %s: %s", filename, e)
            try:
                await chat.send_message(f"Failed to send `{filename}`: {e}")
            except Exception:
                pass
            return False
    try:
        await chat.send_message(f"Failed to send `{filename}` after {retries+1} attempts.")
    except Exception:
        pass
    return False

# ---------------- UI ----------------

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 TXT / Numbers → VCF", callback_data="text_to_vcf")],
        [InlineKeyboardButton("🔢 Count Numbers", callback_data="count")],
        [InlineKeyboardButton("➕ Add Contact", callback_data="add_contact")],
        [InlineKeyboardButton("👤 Rename Contacts", callback_data="rename_contacts")],
        [InlineKeyboardButton("📝 Rename VCF Files", callback_data="rename_files")],
    ])

# ---------------- BOT HANDLERS ----------------

def reset(context):
    context.user_data.clear()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    if not await check_all_memberships(context.bot, user.id):
        # Create keyboard with 3 join buttons + 1 verify button
        keyboard = []
        for channel_info in REQUIRED_CHANNELS:
            keyboard.append([InlineKeyboardButton(f"Join {channel_info['username']}", url=channel_info['invite_url'])])
        keyboard.append([InlineKeyboardButton("Verify Membership", callback_data="check_join")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        channel_list = "\n".join([f"• {channel_info['username']}" for channel_info in REQUIRED_CHANNELS])
        return await update.message.reply_text(
            f"To use this bot, please join all required channels:\n{channel_list}",
            reply_markup=reply_markup
        )

    reset(context)
    if update.message:
        await update.message.reply_text(
            "Aura VCF Bot\n\n"
            "• TXT / Numbers → VCF\n"
            "• Count numbers\n"
            "• Add contact\n"
            "• Rename contacts\n"
            "• Rename VCF files\n\n"
            + CREDIT,
            reply_markup=main_menu()
        )

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central callback-query handler — robust, logs, returns visible feedback quickly."""
    q = update.callback_query
    try:
        await q.answer()  # immediately acknowledge the button press
    except Exception:
        # ignore if already answered
        pass

    logger.info("CallbackQuery received from user=%s data=%s", update.effective_user.id if update.effective_user else None, q.data)
    # quick visual feedback — ephemeral notification (uncomment if you prefer)
    # await q.answer(text="Processing…", show_alert=False)

    try:
        action = q.data
        # operate using q.message where appropriate
        if action == "text_to_vcf":
            reset(context)
            context.user_data["mode"] = "text_to_vcf"
            context.user_data["state"] = "awaiting_contacts_per_file"
            await q.message.reply_text("How many contacts per file?")
            return
        if action == "upload_txt_files":
            # Check if questions are completed
            if not is_awaiting_data(context):
                return await q.message.reply_text("Please complete the configuration questions first.")
            context.user_data["input_method"] = "files"
            context.user_data["state"] = "awaiting_files"
            context.user_data["files"] = []
            await q.message.reply_text("Upload your TXT file(s). After 5 seconds of no new uploads, all files will be processed.")
            return
        if action == "input_raw_numbers":
            # Check if questions are completed
            if not is_awaiting_data(context):
                return await q.message.reply_text("Please complete the configuration questions first.")
            context.user_data["input_method"] = "raw"
            await q.message.reply_text("Paste your numbers (one per line).")
            return
        if action == "back_to_menu":
            reset(context)
            await q.message.reply_text("Back to main menu.", reply_markup=main_menu())
            return
        if action == "count":
            reset(context)
            context.user_data["mode"] = "count"
            context.user_data["state"] = "awaiting_files"
            context.user_data["files"] = []
            await q.message.reply_text("Upload TXT/VCF file(s). After 5 seconds of no new uploads, all files will be processed.")
            return
        if action == "add_contact":
            reset(context)
            context.user_data["mode"] = "add_contact"
            context.user_data["state"] = "awaiting_instruction"
            context.user_data["files"] = []
            await q.message.reply_text("What contact should be added? Send `Name,Phone` (e.g., John,+1234567890).")
            return
        if action == "rename_contacts":
            reset(context)
            context.user_data["mode"] = "rename_contacts"
            context.user_data["state"] = "awaiting_instruction"
            context.user_data["files"] = []
            await q.message.reply_text("What should be the new contact name? (e.g., New Contact)")
            return
        if action == "rename_files":
            reset(context)
            context.user_data["mode"] = "rename_files"
            context.user_data["state"] = "awaiting_instruction"
            context.user_data["files"] = []
            await q.message.reply_text("What should be the new VCF file name? (e.g., contacts)")
            return

        # check membership
        if action == "check_join":
            user = update.effective_user
            if not user:
                return
            if await check_all_memberships(context.bot, user.id):
                reset(context)
                # Edit the existing message instead of sending a new one
                await q.edit_message_text("You are a member of all required channels! You can use the bot.", reply_markup=main_menu())
            else:
                # Create keyboard with 3 join buttons + 1 verify button
                keyboard = []
                for channel_info in REQUIRED_CHANNELS:
                    keyboard.append([InlineKeyboardButton(f"Join {channel_info['username']}", url=channel_info['invite_url'])])
                keyboard.append([InlineKeyboardButton("Verify Membership", callback_data="check_join")])

                reply_markup = InlineKeyboardMarkup(keyboard)
                channel_list = "\n".join([f"• {channel_info['username']}" for channel_info in REQUIRED_CHANNELS])
                # Edit the existing message instead of sending a new one
                await q.edit_message_text(
                    f"You are not a member of all required channels:\n{channel_list}\n\nPlease join all channels and verify again.",
                    reply_markup=reply_markup
                )
            return

        # unknown action
        await q.message.reply_text("Unknown action. Use /start to open the menu.")
    except Exception as e:
        logger.exception("Exception in callback handler: %s", e)
        try:
            # try to notify user about the error
            await q.message.reply_text(f"An error occurred while processing your action: {e}")
        except Exception:
            pass

# FILE handler
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        doc: Document = update.message.document
        if not doc:
            return await update.message.reply_text("No document found in the message.")

        # Check file size before downloading
        size_mb = (doc.file_size or 0) / (1024 * 1024)
        if size_mb > MAX_FILE_MB:
            return await update.message.reply_text(f"File too large ({size_mb:.1f} MB). Limit: {MAX_FILE_MB} MB")

        target, original_name = await _save_doc_to_tmp(doc)
        track_temp_file(context, target)

        chat = update.message.chat
        mode = context.user_data.get("mode")
        input_method = context.user_data.get("input_method")

        # Handle new TXT to VCF flow with file collection
        if mode == "text_to_vcf" and input_method == "files" and is_awaiting_files(context):
            # Collect files for timeout processing
            files = context.user_data.setdefault("files", [])
            files.append(target)
            # Store original filenames
            original_names = context.user_data.setdefault("original_names", [])
            original_names.append(original_name)
            # Cancel existing timeout task if present
            if "timeout_task" in context.user_data:
                try:
                    context.user_data["timeout_task"].cancel()
                except Exception:
                    pass

            # Restart timeout task for text_to_vcf mode
            context.user_data["timeout_task"] = asyncio.create_task(process_after_timeout(chat, context, "text_to_vcf"))

            # Removed confirmation message after file upload
            return

        # if user previously uploaded target files for add/rename/count flows
        if mode in {"add_contact", "rename_contacts", "rename_files", "count"}:
            files = context.user_data.setdefault("files", [])
            files.append(target)
            # Store original filenames
            original_names = context.user_data.setdefault("original_names", [])
            original_names.append(original_name)
            # Cancel existing timeout task if present
            if "timeout_task" in context.user_data:
                try:
                    context.user_data["timeout_task"].cancel()
                except Exception:
                    pass

            # For all modes (add_contact, rename_contacts, rename_files, count), restart timeout task
            if is_awaiting_files(context):
                context.user_data["timeout_task"] = asyncio.create_task(process_after_timeout(chat, context, mode))

            # Removed confirmation message after file upload

        fname_lower = original_name.lower()
        # vcf file processing
        if fname_lower.endswith(".vcf"):
            if mode in {"add_contact", "rename_contacts", "rename_files", "count"}:
                # VCF files are valid for these modes - they will be processed after timeout
                return
            else:
                return await chat.send_message("Please use the menu (/start) to choose an operation.")
        else:
            # treat as TXT/CSV
            if fname_lower.endswith(".txt") or fname_lower.endswith(".csv"):
                content = await asyncio.to_thread(_sync_read_text, target)
                if mode == "text_to_vcf" or mode is None:
                    contacts = []
                    for line in content.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        if re.search(r"[,|:\t]", line):
                            parts = re.split(r"[,|:\t]", line, maxsplit=1)
                        else:
                            parts = line.split(None, 1)
                        if len(parts) == 1:
                            phone = normalize_number(parts[0])
                            contacts.append({"name": "Unknown", "phone": phone})
                        else:
                            name = parts[0].strip()
                            phone = normalize_number(parts[1])
                            contacts.append({"name": name or "Unknown", "phone": phone})
                    if not contacts:
                        return await chat.send_message("No contacts found in the TXT.")
                    vcf_text = build_vcf(contacts)
                    out_path = BASE_TMP / f"{uuid.uuid4().hex[:8]}_export.vcf"
                    track_temp_file(context, out_path)
                    await asyncio.to_thread(_sync_write_text, out_path, vcf_text)
                    await safe_send(chat, out_path, filename="contacts.vcf")
                    # Automatic reset and cleanup
                    await cleanup_temp_files(context)
                    reset(context)
                    return await chat.send_message("Task completed successfully!", reply_markup=main_menu())
        return await update.message.reply_text("File saved. Use the menu (/start) to choose an operation and re-upload if needed.")
    except Exception as e:
        logger.exception("Error in handle_file: %s", e)
        try:
            await update.message.reply_text(f"An error occurred while processing the file: {e}")
        except Exception:
            pass
        return

# TEXT handler
async def text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return await update.message.reply_text("Empty message.")

    mode = context.user_data.get("mode")
    input_method = context.user_data.get("input_method")
    chat = update.message.chat
    logger.info("Text input mode=%s input_method=%s text_len=%d", mode, input_method, len(text))

    # Handle new TXT to VCF flow with raw number collection
    if mode == "text_to_vcf" and input_method == "raw":
        # Extract numbers from the current text input
        numbers = extract_numbers(text)
        if not numbers:
            # Proceed to questions if no numbers found
            await chat.send_message("How many contacts per file?")
            context.user_data["state"] = "awaiting_questions"
            return
        # Process only the numbers from this input
        await process_vcf_generation(chat, context, numbers)
        return

    # Handle new TXT to VCF flow with sequential questions
    if mode == "text_to_vcf":
        state = context.user_data.get("state")
        if state == "awaiting_contacts_per_file":
            try:
                contacts_per_file = int(text)
                if contacts_per_file <= 0:
                    return await chat.send_message("Please enter a positive number for contacts per file.")
                context.user_data["contacts_per_file"] = contacts_per_file
                await chat.send_message("What should be the base file name? (e.g., contacts)")
                context.user_data["state"] = "awaiting_file_name"
                return
            except ValueError:
                return await chat.send_message("Please enter a valid number for contacts per file.")

        if state == "awaiting_file_name":
            file_name = text.strip()
            if not file_name:
                return await chat.send_message("Please enter a non-empty file name.")
            context.user_data["file_name"] = file_name
            await chat.send_message("What should be the base contact name? (e.g., Contact)")
            context.user_data["state"] = "awaiting_base_contact_name"
            return

        if state == "awaiting_base_contact_name":
            base_contact_name = text.strip()
            if not base_contact_name:
                return await chat.send_message("Please enter a non-empty base contact name.")
            context.user_data["base_contact_name"] = base_contact_name

            # Show input options after all questions are answered
            keyboard = [
                [InlineKeyboardButton("📤 Upload TXT Files", callback_data="upload_txt_files")],
                [InlineKeyboardButton("📝 Input Raw Numbers", callback_data="input_raw_numbers")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await chat.send_message("All questions answered! Now choose how to provide numbers:", reply_markup=reply_markup)
            # Set state to awaiting_data to allow file uploads and raw number input
            context.user_data["state"] = "awaiting_data"
            return

    # Prevent legacy processing when awaiting data
    if mode == "text_to_vcf" and is_awaiting_data(context):
        return await chat.send_message("Please use the buttons to upload files or input numbers.")

    # TEXT -> VCF (legacy mode)
    if mode == "text_to_vcf":
        try:
            contacts = []
            for raw in text.splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                if re.search(r"[,|:\t]", raw):
                    parts = re.split(r"[,|:\t]", raw, maxsplit=1)
                else:
                    parts = raw.split(None, 1)
                if len(parts) == 1:
                    phone = normalize_number(parts[0])
                    contacts.append({"name": "Unknown", "phone": phone})
                else:
                    name = parts[0].strip()
                    phone = normalize_number(parts[1])
                    contacts.append({"name": name or "Unknown", "phone": phone})
            if not contacts:
                return await chat.send_message("No valid contacts found in your text.")

            # Generate VCF content
            vcf_text = build_vcf(contacts)

            # Save to file
            out_path = BASE_TMP / f"{uuid.uuid4().hex[:8]}_export.vcf"
            await asyncio.to_thread(_sync_write_text, out_path, vcf_text)

            # Send file
            await safe_send(chat, out_path, filename="contacts.vcf")

            # Automatic reset and cleanup
            await cleanup_temp_files(context)
            reset(context)

            return await chat.send_message("Task completed successfully!", reply_markup=main_menu())
        except Exception as e:
            logger.exception("Error in text_to_vcf processing: %s", e)
            try:
                await chat.send_message(f"An error occurred while processing your text: {e}")
            except Exception:
                pass
            # Ensure cleanup and reset on error
            await cleanup_temp_files(context)
            reset(context)
            return

    # COUNT - removed paste text handling for count mode

    # ADD CONTACT to previously uploaded VCF(s)
    if mode == "add_contact":
        try:
            if re.search(r"[,|:\t]", text):
                parts = re.split(r"[,|:\t]", text, maxsplit=1)
            else:
                parts = text.split(None, 1)
            if len(parts) == 1:
                return await chat.send_message("Please send `Name,Phone` (e.g. John,+9199...)")
            name = parts[0].strip() or "Unknown"
            phone = normalize_number(parts[1])

            # Store contact details for timeout processing
            context.user_data["add_name"] = name
            context.user_data["add_phone"] = phone

            # Set state to allow file uploads with timeout restarts
            context.user_data["state"] = "awaiting_files"
            context.user_data["files"] = []

            # Start timeout task to process all files
            context.user_data["timeout_task"] = asyncio.create_task(process_after_timeout(chat, context, "add_contact"))

            return await chat.send_message(f"Contact '{name}' with phone '{phone}' saved. Upload VCF file(s). After 5 seconds of no new uploads, the contact will be added to all files.")
        except Exception as e:
            logger.exception("Error in add_contact processing: %s", e)
            try:
                await chat.send_message(f"An error occurred while adding contact: {e}")
            except Exception:
                pass
            return

    # RENAME CONTACTS - new contact name
    if mode == "rename_contacts":
        if is_awaiting_instruction(context):
            # Store new contact name and prompt for files
            new_contact_name = text.strip()
            if not new_contact_name:
                return await chat.send_message("Please send a non-empty new contact name.")
            context.user_data["new_contact_name"] = new_contact_name
            context.user_data["state"] = "awaiting_files"
            context.user_data["files"] = []
            return await chat.send_message("New contact name saved. Upload VCF file(s). After 5 seconds of no new uploads, all files will be processed.")
        # If not awaiting instruction, treat as file upload handling (should be handled in handle_file)
        return await chat.send_message("Please use the menu to start the rename contacts flow.")

    # RENAME FILES - new file name
    if mode == "rename_files":
        if is_awaiting_instruction(context):
            # Store new file name and prompt for files
            new_file_name = text.strip()
            if not new_file_name:
                return await chat.send_message("Please send a non-empty new file name.")
            context.user_data["new_file_name"] = new_file_name
            context.user_data["state"] = "awaiting_files"
            context.user_data["files"] = []
            return await chat.send_message("New file name saved. Upload VCF file(s). After 5 seconds of no new uploads, all files will be processed.")
        # If not awaiting instruction, treat as file upload handling (should be handled in handle_file)
        return await chat.send_message("Please use the menu to start the rename files flow.")

async def process_vcf_generation(chat, context, all_numbers: List[str]):
    """Process provided numbers and generate VCF files split by contacts per file."""
    try:
        if not all_numbers:
            await chat.send_message("No phone numbers found to process.")
            return

        logger.info("All VCF files uploaded")

        # Get configuration
        contacts_per_file = context.user_data["contacts_per_file"]
        file_name = context.user_data["file_name"]
        base_contact_name = context.user_data["base_contact_name"]

        # Safety check for contacts_per_file
        if not isinstance(contacts_per_file, int) or contacts_per_file <= 0:
            await chat.send_message("Invalid configuration: contacts_per_file must be a positive integer.")
            return

        # Split into chunks
        total_files = (len(all_numbers) + contacts_per_file - 1) // contacts_per_file
        sent_files = 0

        for i in range(total_files):
            start_idx = i * contacts_per_file
            end_idx = start_idx + contacts_per_file
            chunk_numbers = all_numbers[start_idx:end_idx]

            # Build contacts for this chunk
            contacts = []
            for idx, phone in enumerate(chunk_numbers, start=1):
                contact_name = f"{base_contact_name} {start_idx + idx}"
                contacts.append({"name": contact_name, "phone": phone})

            # Generate VCF content
            vcf_text = build_vcf(contacts)

            # Save to file
            file_suffix = i + 1
            filename = f"{file_name}_{file_suffix}.vcf"
            out_path = BASE_TMP / f"{uuid.uuid4().hex[:8]}_{filename}"
            track_temp_file(context, out_path)
            await asyncio.to_thread(_sync_write_text, out_path, vcf_text)

            # Send file
            ok = await safe_send(chat, out_path, filename=filename)
            if ok:
                sent_files += 1

        await chat.send_message(f"Generated {sent_files} VCF file(s) with {contacts_per_file} contacts per file.")

        # Automatic reset and cleanup
        await cleanup_temp_files(context)
        reset(context)

        return await chat.send_message("Task completed successfully!", reply_markup=main_menu())
    except Exception as e:
        logger.exception("Error in process_vcf_generation: %s", e)
        try:
            await chat.send_message(f"An error occurred while generating VCF files: {e}")
        except Exception:
            pass

        # Reset and cleanup on error
        await cleanup_temp_files(context)
        reset(context)

        return await chat.send_message("Task completed successfully!", reply_markup=main_menu())

async def process_after_timeout(chat, context, mode: str):
    """Process files after 5 seconds of no new uploads."""
    try:
        await asyncio.sleep(5)
        # Check if still awaiting files
        if not is_awaiting_files(context):
            return
        files: List[Path] = context.user_data.get("files", [])
        if not files:
            return
        logger.info("Timeout reached, processing %d files for mode %s", len(files), mode)

        # For add_contact mode, process all files
        if mode == "add_contact":
            name = context.user_data.get("add_name")
            phone = context.user_data.get("add_phone")
            if not name or not phone:
                await chat.send_message("No contact details found. Please start the flow again.")
                await cleanup_temp_files(context)
                reset(context)
                return

            added = {"name": name, "phone": phone}

            async def _modify_add(p: Path) -> Optional[Path]:
                try:
                    content = await asyncio.to_thread(_sync_read_text, p)
                    contacts = parse_vcf(content)
                    contacts.append(added)
                    new_vcf = build_vcf(contacts)
                    out_path = BASE_TMP / f"{uuid.uuid4().hex[:8]}_{p.name}"
                    track_temp_file(context, out_path)
                    await asyncio.to_thread(_sync_write_text, out_path, new_vcf)
                    return out_path
                except Exception as e:
                    logger.exception("Failed to add contact to %s: %s", p.name, e)
                    try:
                        await chat.send_message(f"Failed to modify {p.name}: {e}")
                    except Exception:
                        pass
                    # Ensure cleanup and reset on error
                    await cleanup_temp_files(context)
                    reset(context)
                    return None

            tasks = [asyncio.create_task(_modify_add(p)) for p in files]
            results = await asyncio.gather(*tasks)
            original_names = context.user_data.get("original_names", [])
            for i, r in enumerate(results):
                if r:
                    await safe_send(chat, r, filename=original_names[i])
            # Automatic reset and cleanup
            await cleanup_temp_files(context)
            reset(context)
            return await chat.send_message("Task completed successfully!", reply_markup=main_menu())

        # For rename_contacts mode, process all files with global contact numbering
        elif mode == "rename_contacts":
            new_contact_name = context.user_data.get("new_contact_name")
            if not new_contact_name:
                await chat.send_message("No new contact name found. Please start the flow again.")
                await cleanup_temp_files(context)
                reset(context)
                return

            # Calculate global contact numbering across all files
            global_contact_counter = 1

            async def _modify_rename_contacts(p: Path) -> Optional[Path]:
                nonlocal global_contact_counter
                try:
                    content = await asyncio.to_thread(_sync_read_text, p)
                    contacts = parse_vcf(content)

                    if not contacts:
                        return None

                    # Rename contacts with global numbering
                    for contact in contacts:
                        contact["name"] = f"{new_contact_name} {global_contact_counter}"
                        global_contact_counter += 1

                    new_vcf = build_vcf(contacts)
                    out_path = BASE_TMP / f"{uuid.uuid4().hex[:8]}_{p.name}"
                    track_temp_file(context, out_path)
                    await asyncio.to_thread(_sync_write_text, out_path, new_vcf)
                    return out_path
                except Exception as e:
                    logger.exception("Failed to rename contacts in %s: %s", p.name, e)
                    try:
                        await chat.send_message(f"Failed to modify {p.name}: {e}")
                    except Exception:
                        pass
                    # Ensure cleanup and reset on error
                    await cleanup_temp_files(context)
                    reset(context)
                    return None

            tasks = [asyncio.create_task(_modify_rename_contacts(p)) for p in files]
            results = await asyncio.gather(*tasks)
            original_names = context.user_data.get("original_names", [])
            for i, r in enumerate(results):
                if r:
                    await safe_send(chat, r, filename=original_names[i])
            # Automatic reset and cleanup
            await cleanup_temp_files(context)
            reset(context)
            return await chat.send_message("Task completed successfully!", reply_markup=main_menu())

        # For rename_files mode, process all files with batch renaming
        elif mode == "rename_files":
            new_file_name = context.user_data.get("new_file_name")
            if not new_file_name:
                await chat.send_message("No new file name found. Please start the flow again.")
                await cleanup_temp_files(context)
                reset(context)
                return

            async def _modify_rename_files(p: Path, file_index: int) -> Optional[Path]:
                try:
                    # Ensure .vcf extension
                    if not new_file_name.lower().endswith('.vcf'):
                        new_filename = f"{new_file_name}_{file_index + 1}.vcf"
                    else:
                        new_filename = f"{new_file_name[:-4]}_{file_index + 1}.vcf"

                    out_path = BASE_TMP / f"{uuid.uuid4().hex[:8]}_{new_filename}"
                    track_temp_file(context, out_path)
                    await asyncio.to_thread(_sync_copy_file, p, out_path)
                    return out_path, new_filename
                except Exception as e:
                    logger.exception("Failed to rename file %s: %s", p.name, e)
                    try:
                        await chat.send_message(f"Failed to rename {p.name}: {e}")
                    except Exception:
                        pass
                    # Ensure cleanup and reset on error
                    await cleanup_temp_files(context)
                    reset(context)
                    return None

            tasks = [asyncio.create_task(_modify_rename_files(p, i)) for i, p in enumerate(files)]
            results = await asyncio.gather(*tasks)
            for r in results:
                if r:
                    await safe_send(chat, r[0], filename=r[1])
            # Automatic reset and cleanup
            await cleanup_temp_files(context)
            reset(context)
            return await chat.send_message("Task completed successfully!", reply_markup=main_menu())

        # For count mode, process all files and count unique numbers
        elif mode == "count":
            unique_numbers = set()
            total_contacts = 0

            async def _count_from_file(p: Path) -> Tuple[int, int]:
                try:
                    content = await asyncio.to_thread(_sync_read_text, p)
                    fname_lower = p.name.lower()

                    if fname_lower.endswith('.vcf'):
                        contacts = parse_vcf(content)
                        total_contacts = len(contacts)
                        numbers = [c["phone"] for c in contacts]
                        return total_contacts, len(set(numbers))
                    else:
                        # Treat as TXT/CSV
                        numbers = extract_numbers(content)
                        return 0, len(set(numbers))
                except Exception as e:
                    logger.exception("Failed to count numbers from %s: %s", p.name, e)
                    try:
                        await chat.send_message(f"Failed to process {p.name}: {e}")
                    except Exception:
                        pass
                    return 0, 0

            tasks = [asyncio.create_task(_count_from_file(p)) for p in files]
            results = await asyncio.gather(*tasks)

            for contacts_count, numbers_count in results:
                total_contacts += contacts_count

            # Calculate unique numbers across all files
            all_numbers = []
            for p in files:
                content = await asyncio.to_thread(_sync_read_text, p)
                fname_lower = p.name.lower()
                if fname_lower.endswith('.vcf'):
                    all_numbers.extend([c["phone"] for c in parse_vcf(content)])
                else:
                    all_numbers.extend(extract_numbers(content))

            unique_numbers = set(all_numbers)

            # Send count result
            if total_contacts > 0:
                await chat.send_message(f"Found {total_contacts} contact(s) and {len(unique_numbers)} unique phone number(s) across all files.")
            else:
                await chat.send_message(f"Found {len(unique_numbers)} unique phone number(s) across all files.")

            # Automatic reset and cleanup
            await cleanup_temp_files(context)
            reset(context)
            return await chat.send_message("Task completed successfully!", reply_markup=main_menu())

        # For text_to_vcf mode, process all files and generate VCF files
        elif mode == "text_to_vcf":
            all_numbers = []

            async def _extract_numbers_from_file(p: Path) -> List[str]:
                try:
                    content = await asyncio.to_thread(_sync_read_text, p)
                    return extract_numbers(content)
                except Exception as e:
                    logger.exception("Failed to extract numbers from %s: %s", p.name, e)
                    try:
                        await chat.send_message(f"Failed to process {p.name}: {e}")
                    except Exception:
                        pass
                    return []

            tasks = [asyncio.create_task(_extract_numbers_from_file(p)) for p in files]
            results = await asyncio.gather(*tasks)

            for numbers in results:
                all_numbers.extend(numbers)

            if not all_numbers:
                await chat.send_message("No phone numbers found in any of the uploaded files.")
                # Automatic reset and cleanup
                await cleanup_temp_files(context)
                reset(context)
                return await chat.send_message("Task completed successfully!", reply_markup=main_menu())

            # Process all numbers together using existing function
            await process_vcf_generation(chat, context, all_numbers)

        else:
            # Unknown mode
            await cleanup_temp_files(context)
            reset(context)
            return await chat.send_message("Task completed successfully!")

    except asyncio.CancelledError:
        # Task was cancelled, do nothing
        pass
    except Exception as e:
        logger.exception("Error in process_after_timeout: %s", e)
        try:
            await chat.send_message(f"An error occurred during timeout processing: {e}")
        except Exception:
            pass
        # Reset and cleanup on error
        await cleanup_temp_files(context)
        reset(context)
        return await chat.send_message("Task completed successfully!")

def setup_handlers(app: ApplicationBuilder):
    """Setup all bot handlers"""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input))
