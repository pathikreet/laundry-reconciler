#!/bin/bash

# 1. Check if the user provided a path
if [ -z "$1" ]; then
    echo "Usage: ./parse_batch.sh <path_to_image_file_OR_directory>"
    exit 1
fi

TARGET="$1"
FILES_TO_PROCESS=()

# 2. Determine if the input is a single file or a directory
if [ -f "$TARGET" ]; then
    echo "Single file detected. Starting processing..."
    FILES_TO_PROCESS+=("$TARGET")
elif [ -d "$TARGET" ]; then
    echo "Directory detected. Starting batch processing..."
    # Gather all images in the directory
    for file in "$TARGET"/*.jpg "$TARGET"/*.jpeg "$TARGET"/*.png; do
        [ -e "$file" ] && FILES_TO_PROCESS+=("$file")
    done
else
    echo "Error: '$TARGET' is not a valid file or directory."
    exit 1
fi

# Check if we found any files to process
if [ ${#FILES_TO_PROCESS[@]} -eq 0 ]; then
    echo "No valid image files found to process."
    exit 1
fi

# Initialize arrays and counters
FAILED_FILES=()
TOTAL_FILES=0
SUCCESS_FILES=0

# 3. Loop through the files (runs once for a single file, or multiple times for a directory)
for file in "${FILES_TO_PROCESS[@]}"; do
    
    ((TOTAL_FILES++))
    echo "Parsing: $file"
    
    # Run Gemini CLI and filter for commas, saving output to a variable
    PARSED_DATA=$(gemini /tumbledry:parse "$file" | grep ",")
    
    # Check if we got valid CSV data back
    if [ -z "$PARSED_DATA" ]; then
        echo "   -> ERROR: Parsing failed or no valid data found."
        FAILED_FILES+=("$file")
    else
        ((SUCCESS_FILES++))
        
        # Pass the valid data to awk to be routed to the correct file
        echo "$PARSED_DATA" | awk -F',' '{
            date_val = $5
            split(date_val, date_parts, "/")
            month = date_parts[2]
            
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

            if (m_name != "Unknown") {
                filename = "Delivery_notes_" m_name ".csv"
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
echo "✅ Successfully parsed $SUCCESS_FILES out of $TOTAL_FILES files."

# Print out any failed files
if [ ${#FAILED_FILES[@]} -ne 0 ]; then
    echo "⚠️ The following files failed to parse and need manual review:"
    for failed_file in "${FAILED_FILES[@]}"; do
        echo " - $failed_file"
    done
fi