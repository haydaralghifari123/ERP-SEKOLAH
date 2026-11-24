# Uji pasang tunggal: buang DB uji_<modul>, pasang modul itu saja dengan tesnya.
# Pemakaian: .\scripts\uji_tunggal.ps1 -Modul nti_edu_base
param(
    [Parameter(Mandatory = $true)][string]$Modul
)

$python = "D:/Program Files/python/python.exe"
$odoo = "D:/Program Files/server/odoo-bin"
$konfigurasi = "D:\odoo2\odoo.conf"
$konfigurasiUji = "D:\odoo2\.odoo-test.conf"
$dropdb = "D:/Program Files/PostgreSQL/bin/dropdb.exe"
$db = "uji_$Modul"

# Kata sandi dibaca dari odoo.conf, tidak pernah dicetak.
$baris = Select-String -Path $konfigurasi -Pattern '^\s*db_password\s*=\s*(.*)$' | Select-Object -First 1
if ($baris) { $env:PGPASSWORD = $baris.Matches[0].Groups[1].Value.Trim() }

# Konfigurasi turunan (di-ignore git): salinan odoo.conf dengan aplikasi produktivitas otomatis dimatikan,
# supaya hanya modul yang diuji (dan dependensinya) terpasang. odoo.conf asli tidak diubah.
$isi = Get-Content -Path $konfigurasi | Where-Object { $_ -notmatch '^\s*default_productivity_apps\s*=' }
$isi += 'default_productivity_apps = False'
Set-Content -Path $konfigurasiUji -Value $isi -Encoding ASCII

& $dropdb -h localhost -U odoo --if-exists $db
if ($LASTEXITCODE -ne 0) { Write-Error "Gagal membuang DB $db"; exit 1 }

$log = & $python $odoo --config=$konfigurasiUji -d $db -i $Modul --test-tags "/$Modul" `
    --stop-after-init --http-port 8079 --db-filter=.* --log-level=test 2>&1 | ForEach-Object { "$_" }
$log | ForEach-Object { Write-Host $_ }

# (?<!\d) mencegah "10 failed" / "20 failed" lolos sebagai "0 failed".
if ($log -match '(?<!\d)0 failed, 0 error\(s\) of [1-9]\d* tests') {
    Write-Host "LULUS: $Modul"
    exit 0
}
Write-Host "GAGAL: $Modul"
exit 1
