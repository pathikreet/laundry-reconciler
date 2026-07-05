#!/bin/bash

# ── Help / Usage ──────────────────────────────────────────
show_help() {
    cat << 'EOF'
USAGE
    ./scripts/parse_batch.sh <path>
    ./scripts/parse_batch.sh --help

DESCRIPTION
    Converts handwritten runner delivery notepad photos into structured CSV
    files using Gemini AI OCR. Supports single files or entire directories.

    Each image is sent to Gemini CLI (via the /tumbledry:parse custom command),
    which reads the handwriting and returns structured CSV rows. Rows are then
    routed to month-specific output files based on the parsed date (column 5).

ARGUMENTS
    <path>      Path to a single image file (.jpg, .jpeg, .png) or a directory
                containing image files. When a directory is given, all image
                files inside it are processed.

    --help      Show this help message and exit.

OPTIONS
    The script has no additional flags. Behavior is determined by the input:

    Single file:    ./scripts/parse_batch.sh /path/to/notepad_page.jpg
    Directory:      ./scripts/parse_batch.sh /path/to/notepad_photos/

OUTPUT
    CSV files are written to the CURRENT WORKING DIRECTORY:

        Delivery_notes_January_2026.csv     Entries dated in January 2026
        Delivery_notes_February_2026.csv    Entries dated in February 2026
        ...                                 (one file per month+year)
        Delivery_notes_Unsorted.csv         Rows where the date could not be parsed

    Tip: Run from a dedicated output folder to keep files organized:
        cd data/notepad_csvs && ../../scripts/parse_batch.sh /path/to/photos/

IDEMPOTENCY
    The script tracks processed files in a hidden state file
    (.processed_images.log) in the image source directory. Re-running skips
    already-processed images. Delete the state file to force reprocessing.

PREREQUISITES
    1. Antigravity CLI installed and authenticated:
         curl -fsSL https://antigravity.google/cli/install.sh | bash
         agy auth login

    2. Custom /tumbledry-parse skill registered globally:
         # macOS / Linux / Windows (WSL)
         mkdir -p ~/.gemini/antigravity-cli/skills/tumbledry-parse
         cp scripts/skills/tumbledry-parse/SKILL.md ~/.gemini/antigravity-cli/skills/tumbledry-parse/SKILL.md

         # Windows (PowerShell)
         New-Item -ItemType Directory -Force "$env:USERPROFILE\.gemini\antigravity-cli\skills\tumbledry-parse"
         Copy-Item scripts\skills\tumbledry-parse\SKILL.md "$env:USERPROFILE\.gemini\antigravity-cli\skills\tumbledry-parse\SKILL.md"

    3. Image files in .jpg, .jpeg, or .png format.

EXAMPLES
    # Parse a single photo
    ./scripts/parse_batch.sh ~/photos/notepad_nov_01.jpg

    # Parse all photos in a folder
    ./scripts/parse_batch.sh ~/photos/november/

    # Parse into a dedicated output directory
    cd data/notepad_csvs
    ../../scripts/parse_batch.sh ~/photos/november/

EXIT CODES
    0   Success (or no new files to process)
    1   Invalid arguments or input path
EOF
    exit 0
}

# Check for --help flag
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_help
fi

# 1. Check if the user provided a path
if [ -z "$1" ]; then
    echo "Usage: ./scripts/parse_batch.sh <path_to_image_file_OR_directory>"
    echo "       ./scripts/parse_batch.sh --help    Show detailed usage guide"
    exit 1
fi

TARGET="$1"
FILES_TO_PROCESS=()

# Determine state file location based on whether target is a file or directory
if [ -d "$TARGET" ]; then
    STATE_FILE="$TARGET/.processed_images.log"
else
    STATE_FILE="$(dirname "$TARGET")/.processed_images.log"
fi

# Create state file if it doesn't exist
touch "$STATE_FILE"

# 2. Determine if the input is a single file or a directory
if [ -f "$TARGET" ]; then
    FILENAME_ONLY=$(basename "$TARGET")
    if grep -Fxq "$FILENAME_ONLY" "$STATE_FILE"; then
        echo "File '$TARGET' has already been processed. Skipping."
    else
        echo "Single file detected. Starting processing..."
        FILES_TO_PROCESS+=("$TARGET")
    fi
elif [ -d "$TARGET" ]; then
    echo "Directory detected. Scanning for new files..."
    # Gather all images in the directory
    for file in "$TARGET"/*.jpg "$TARGET"/*.jpeg "$TARGET"/*.png; do
        if [ -e "$file" ]; then
            FILENAME_ONLY=$(basename "$file")
            # Check if file is already processed
            if grep -Fxq "$FILENAME_ONLY" "$STATE_FILE"; then
                continue # Skip already processed files
            fi
            FILES_TO_PROCESS+=("$file")
        fi
    done
else
    echo "Error: '$TARGET' is not a valid file or directory."
    exit 1
fi

# Check if we found any files to process
if [ ${#FILES_TO_PROCESS[@]} -eq 0 ]; then
    echo "No new image files found to process."
    exit 0
fi

# Initialize arrays and counters
FAILED_FILES=()
TOTAL_FILES=0
SUCCESS_FILES=0

# 3. Loop through the files (runs once for a single file, or multiple times for a directory)
for file in "${FILES_TO_PROCESS[@]}"; do

    ((TOTAL_FILES++))
    echo "Parsing: $file"

    # Resolve the file path to an absolute path
    ABS_FILE=$(realpath "$file")

    # Run Antigravity CLI (agy) and filter for commas, saving output to a variable
    # Stdin is redirected from /dev/null to prevent the CLI from hanging in headless scripts
    PARSED_DATA=$(agy -p "/tumbledry-parse @$ABS_FILE" --dangerously-skip-permissions < /dev/null | grep ",")

    # Check if we got valid CSV data back
    if [ -z "$PARSED_DATA" ]; then
        echo "   -> ERROR: Parsing failed or no valid data found."
        FAILED_FILES+=("$file")
    else
        ((SUCCESS_FILES++))

        # Mark as processed immediately on success
        basename "$file" >> "$STATE_FILE"

        # Pass the valid data to awk to be routed to the correct file (appending to end of file)
        echo "$PARSED_DATA" | awk -F',' '{
            date_val = $5
            split(date_val, date_parts, /[\/\-]/)
            month = date_parts[2]
            year = date_parts[3]

            if (month == "01" || month == "1") m_name = "January"
            else if (month == "02" || month == "2") m_name = "February"
            else if (month == "03" || month == "3") m_name = "March"
            else if (month == "04" || month == "4") m_name = "April"
            else if (month == "05" || month == "5") m_name = "May"
            else if (month == "06" || month == "6") m_name = "June"
            else if (month == "07" || month == "7") m_name = "July"
            else if (month == "08" || month == "8") m_name = "August"
            else if (month == "09" || month == "9") m_name = "September"
            else if (month == "10") m_name = "October"
            else if (month == "11") m_name = "November"
            else if (month == "12") m_name = "December"
            else m_name = "Unknown"

            if (m_name != "Unknown" && year != "") {
                filename = "Delivery_notes_" m_name "_" year ".csv"
            } else {
                filename = "Delivery_notes_Unsorted.csv"
            }

            if (!date_printed) {
                print "   -> Parsed Date: " date_val " | Routing to: " filename
                date_printed = 1
            }

            print $0 >> filename
        }'
    fi
done

echo "-----------------------------------"
echo "Processing complete!"

# Print the success ratio
echo "✅ Successfully parsed $SUCCESS_FILES out of $TOTAL_FILES new files."

# Print out any failed files
if [ ${#FAILED_FILES[@]} -ne 0 ]; then
    echo "⚠️ The following files failed to parse and need manual review:"
    for failed_file in "${FAILED_FILES[@]}"; do
        echo " - $failed_file"
    done
fi