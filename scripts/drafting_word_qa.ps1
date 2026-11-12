param([string]$DraftName='real-draft')
$ErrorActionPreference='Stop'
$draftQa=Join-Path $PSScriptRoot '..\qa\drafting-workspace-20261112'
$draftQa=[IO.Path]::GetFullPath($draftQa)
$draftWord=$null
$draftDoc=$null
try {
    $draftWord=New-Object -ComObject Word.Application
    Write-Output 'Word automation started'
    $draftWord.Visible=$false
    $draftWord.DisplayAlerts=0
    foreach($draftName in @($DraftName)){
        $draftDoc=$draftWord.Documents.Open((Join-Path $draftQa ($draftName+'.docx')),$false,$true)
        Write-Output ('Opened '+$draftName)
        $draftDoc.Repaginate()
        Write-Output 'Pagination completed'
        $draftDoc.SaveAs2((Join-Path $draftQa ($draftName+'.pdf')),17)
        Write-Output 'PDF export completed'
        [PSCustomObject]@{File=$draftName;Pages=$draftDoc.ComputeStatistics(2)} | ConvertTo-Json -Compress
        $draftDoc.Close(0)
        $draftDoc=$null
    }
} finally {
    if($null -ne $draftDoc){$draftDoc.Close(0)}
    if($null -ne $draftWord){$draftWord.Quit()}
}
