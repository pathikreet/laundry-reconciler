# parse_batch.ps1
# Usage: .\scripts\parse_batch.ps1 <path_to_image_or_directory>

param (
    [Parameter(Mandatory=$false, Position=0)]
    [string]$Target,
    
    [switch]$Help
)

$HelpContent = @"
USAGE
    .\scripts\parse_batch.ps1 <path>
    .\scripts\parse_batch.ps1 -Help

DESCRIPTION
    Converts handwritten runner delivery notepad photos into structured CSV
    files using Antigravity AI OCR. Supports single files or entire directories.

    Each image is sent to Antigravity CLI (via the /tumbledry-parse custom skill),
    which reads the handwriting and returns structured CSV rows. Rows are then
    routed to month-specific output files based on the parsed date (column 5).

ARGUMENTS
    <path>      Path to a single image file (.jpg, .jpeg, .png) or a directory
                containing image files. When a directory is given, all image
                files inside it are processed.

    -Help       Show this help message and exit.

OUTPUT
    CSV files are written to the CURRENT WORKING DIRECTORY:
        Delivery_notes_January_2026.csv     Entries dated in January 2026
        Delivery_notes_February_2026.csv    Entries dated in February 2026
        ...                                 (one file per month+year)
        Delivery_notes_Unsorted.csv         Rows where the date could not be parsed

PREREQUISITES
    1. Antigravity CLI installed and authenticated:
         irm https://antigravity.google/cli/install.ps1 | iex
         agy auth login

    2. Custom /tumbledry-parse skill registered globally:
         New-Item -ItemType Directory -Force "`$env:USERPROFILE\.gemini\antigravity-cli\skills\tumbledry-parse"
         Copy-Item scripts\skills\tumbledry-parse\SKILL.md "`$env:USERPROFILE\.gemini\antigravity-cli\skills\tumbledry-parse\SKILL.md"
"@

if ($Help -or ($null -eq $Target -and $args.Count -eq 0)) {
    Write-Output $HelpContent
    exit 0
}

if ($null -eq $Target) {
    Write-Error "Usage: .\scripts\parse_batch.ps1 <path_to_image_file_OR_directory>"
    exit 1
}

# Resolve target to absolute path
$ResolvedTarget = Resolve-Path $Target -ErrorAction SilentlyContinue
if ($null -eq $ResolvedTarget) {
    Write-Error "Error: '$Target' is not a valid file or directory."
    exit 1
}
$Target = $ResolvedTarget.Path

$FilesToProcess = @()
$StateFile = ""

# Determine state file location
if (Test-Path $Target -PathType Container) {
    $StateFile = Join-Path $Target ".processed_images.log"
} else {
    $parentDir = Split-Path $Target -Parent
    $StateFile = Join-Path $parentDir ".processed_images.log"
}

# Create state file if it doesn't exist
if (!(Test-Path $StateFile)) {
    New-Item -Path $StateFile -ItemType File -Force | Out-Null
}

# Read state file to find already processed files
$ProcessedFiles = @()
if (Test-Path $StateFile) {
    $ProcessedFiles = Get-Content $StateFile -ErrorAction SilentlyContinue
}

# Collect files to process
if (Test-Path $Target -PathType Leaf) {
    $filename = Split-Path $Target -Leaf
    if ($ProcessedFiles -contains $filename) {
        Write-Output "File '$Target' has already been processed. Skipping."
    } else {
        Write-Output "Single file detected. Starting processing..."
        $FilesToProcess += $Target
    }
} elseif (Test-Path $Target -PathType Container) {
    Write-Output "Directory detected. Scanning for new files..."
    $images = Get-ChildItem -Path $Target -File -Include *.jpg, *.jpeg, *.png -ErrorAction SilentlyContinue
    foreach ($img in $images) {
        if ($ProcessedFiles -contains $img.Name) {
            continue
        }
        $FilesToProcess += $img.FullName
    }
}

if ($FilesToProcess.Count -eq 0) {
    Write-Output "No new image files found to process."
    exit 0
}

$FailedFiles = @()
$TotalFiles = 0
$SuccessFiles = 0

# Helper function to map month numbers to names
function Get-MonthName($m) {
    switch ($m) {
        "01" { return "January" }
        "1"  { return "January" }
        "02" { return "February" }
        "2"  { return "February" }
        "03" { return "March" }
        "3"  { return "March" }
        "04" { return "April" }
        "4"  { return "April" }
        "05" { return "May" }
        "5"  { return "May" }
        "06" { return "June" }
        "6"  { return "June" }
        "07" { return "July" }
        "7"  { return "July" }
        "08" { return "August" }
        "8"  { return "August" }
        "09" { return "September" }
        "9"  { return "September" }
        "10" { return "October" }
        "11" { return "November" }
        "12" { return "December" }
        default { return "Unknown" }
    }
}

foreach ($file in $FilesToProcess) {
    $TotalFiles++
    Write-Output "Parsing: $file"
    
    # Run Antigravity CLI (piping $null to prevent stdin blocking)
    $ParsedData = $null | & agy -p "/tumbledry-parse @$file" --dangerously-skip-permissions 2>&1
    
    # Filter lines that look like CSV (containing comma)
    $CsvLines = @()
    foreach ($line in $ParsedData) {
        $lineStr = "$line".Trim()
        if ($lineStr -like "*,*") {
            $CsvLines += $lineStr
        }
    }
    
    if ($CsvLines.Count -eq 0) {
        Write-Output "   -> ERROR: Parsing failed or no valid data found."
        $FailedFiles += $file
    } else {
        $SuccessFiles++
        
        # Mark as processed
        $filename = Split-Path $file -Leaf
        Add-Content -Path $StateFile -Value $filename
        
        # Process and route each CSV line
        $datePrinted = $false
        foreach ($row in $CsvLines) {
            $cols = $row.Split(',')
            $filenameToRoute = "Delivery_notes_Unsorted.csv"
            $dateVal = ""
            
            if ($cols.Count -ge 5) {
                $dateVal = $cols[4].Trim()
                # Split date by / or -
                $parts = $dateVal -split '[\/\-]'
                if ($parts.Count -ge 3) {
                    $month = $parts[1]
                    $year = $parts[2]
                    $mName = Get-MonthName $month
                    if ($mName -ne "Unknown" -and $year -ne "") {
                        $filenameToRoute = "Delivery_notes_$(${mName})_$(${year}).csv"
                    }
                }
            }
            
            if (!$datePrinted) {
                Write-Output "   -> Parsed Date: $dateVal | Routing to: $filenameToRoute"
                $datePrinted = $true
            }
            
            Add-Content -Path $filenameToRoute -Value $row
        }
    }
}

Write-Output "-----------------------------------"
Write-Output "Processing complete!"
Write-Output "✅ Successfully parsed $SuccessFiles out of $TotalFiles new files."

if ($FailedFiles.Count -ne 0) {
    Write-Output "⚠️ The following files failed to parse and need manual review:"
    foreach ($failed in $FailedFiles) {
        Write-Output " - $failed"
    }
}
