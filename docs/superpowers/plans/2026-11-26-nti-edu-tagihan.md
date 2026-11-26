# `nti_edu_tagihan` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modul baru `nti_edu_tagihan` (app "Keuangan Sekolah"): data master biaya yang diatur admin, tagihan siswa
berbasis invoice Odoo (otomatis & manual), potongan, cicilan, denda, pembayaran tunai & konfirmasi transfer dari
portal, kartu SPP, tunggakan.

**Architecture:** Addon baru `D:/odoo2/nti_edu_tagihan`, depends `nti_edu_base`, `account`, `portal`. Tagihan =
`account.move` out_invoice dengan field `nti_edu_*`; pembayaran = `account.payment` lewat wizard register Odoo.
Grup tagihan **tidak** meng-imply grup akuntansi: mereka punya ACL baca sendiri + rule cakupan, dan semua penulisan
akuntansi lewat metode modul `sudo()` di balik penjaga grup+unit. Mesin pembuatan/denda/pengingat = `ir.cron`.

**Tech Stack:** Odoo 18.0 Community (`account`, `portal`, `mail`), Python 3, QWeb (laporan PDF & portal), tour
`web_tour`.

**Spec:** `D:/odoo2/docs/superpowers/specs/2026-11-26-nti-edu-tagihan-design.md` (induk:
`2026-11-24-nti-edu-arsitektur-design.md` §I.4).

## Global Constraints

- Odoo **18.0 Community** saja; tanpa Enterprise/OCA.
- `__manifest__.py`: `'depends': ['nti_edu_base', 'account', 'portal']`, `'version': '18.0.1.0.0'`,
  `'license': 'LGPL-3'`, `'category': 'Education'`, `'application': True`, tanpa `auto_install`. Tidak depend ke modul
  fitur NTI Edu lain (termasuk `nti_edu_pegawai`).
- Field baru di model standar (`account.move`, `account.payment`, `res.company`, `res.partner`) **selalu** berawalan
  `nti_edu_`; model baru `nti_edu.tagihan.*`; field base tidak didefinisikan ulang.
- Setiap pilihan yang bisa berbeda antar sekolah = data master/pengaturan, bukan konstanta di kode (spec §4.2).
  Tidak ada `safe_eval`.
- Pengaturan kebijakan unit (`res.company.nti_edu_*` tagihan) hanya ditulis `base.group_system`; master biaya oleh
  `group_tagihan_admin`.
- Grup tagihan tidak meng-imply `account.group_account_*`. Penulisan `account.move`/`account.payment` oleh grup tagihan
  hanya lewat metode modul (`sudo()` setelah `_nti_edu_cek_hak(grup, company)`).
- Nama field/model/pesan/komentar Bahasa Indonesia; pesan galat lewat `_()`.
- View Odoo 18: `<list>`, ekspresi `invisible=`/`readonly=`, kanban `t-name="card"`.
- Tes: `@tagged('post_install', '-at_install')`, data dibuat sendiri (tidak bergantung demo, tetap lulus dengan
  demo); tanggal dibekukan dengan `freezegun.freeze_time` bila logika bergantung hari ini.
- Commit tanpa `Co-Authored-By` dan tanpa menyebut Claude; pesan `nti_edu_tagihan: <ringkasan Bahasa Indonesia>`.
- Perintah tes (PowerShell), DB tes **`nti_tagihan_tes`** (Task 1 `-i`, berikutnya `-u nti_edu_tagihan`):
  ```
  & "D:/Program Files/python/python.exe" "D:/Program Files/server/odoo-bin" --config=D:/odoo2/.odoo-test.conf -d nti_tagihan_tes -i nti_edu_tagihan --test-tags /nti_edu_tagihan --stop-after-init --http-port 8079 --db-filter=.* --log-level=test
  ```
  Lulus = `0 failed, 0 error(s)`. Akhir tiap task: suite `/nti_edu_tagihan` + `scripts/uji_tunggal.ps1 -Modul
  nti_edu_tagihan`; task yang mengubah `nti_edu_base` juga menjalankan `/nti_edu_base` dan `/nti_edu_pegawai`.
- Jangan sentuh `odoo.conf`, DB `odoo2`, atau Odoo pengguna / ngrok di port 8070.

## Review Focus

1. Jadwal harian dijalankan dua kali di hari yang sama, atau bendahara menekan Buat Tagihan setelah jadwal jalan →
   tidak ada tagihan ganda dan tidak ada galat yang menghentikan siswa lain (Task 4).
2. Sekolah memasang modul bulan November dengan `tagihan_mulai` = 1 Nov → tidak ada SPP Juli–Oktober, tidak ada uang
   pangkal untuk siswa lama, tidak ada denda atas apa pun sebelum November (Task 4, 9).
3. Wali dengan dua anak (SMP & SMA) mengirim konfirmasi berisi tagihan dua unit, atau memalsukan id tagihan anak lain
   di form portal → ditolak server (Task 7, 11).
4. Beasiswa 100% SPP → tagihan nol tetap terbit dan langsung lunas, tidak muncul di tunggakan, tidak didenda (Task 4,
   9, 10).
5. Bendahara SMP pada mode bawaan membuka Keuangan Sekolah lalu mencoba membaca tagihan vendor/jurnal lain unitnya
   atau tagihan SMA lewat RPC → tidak terlihat (Task 3).

---

### Task 1: Kerangka modul, grup, data master konfigurasi, komponen biaya

**Files:**
- Create: `nti_edu_tagihan/__init__.py`, `__manifest__.py`, `models/__init__.py`, `models/master.py`
  (bulan, periode, aturan denda/cicilan/masuk, rekening, alasan tolak/hapus), `models/komponen.py`,
  `security/nti_edu_tagihan_security.xml`, `security/ir.model.access.csv`, `data/master_data.xml`,
  `views/master_views.xml`, `views/komponen_views.xml`, `views/menu.xml`, `tests/__init__.py`, `tests/common.py`,
  `tests/test_master.py`

**Interfaces:**
- Produces:
  - Kategori `nti_edu_tagihan.module_category_nti_edu_tagihan` ("NTI Edu / Tagihan"); grup
    `group_tagihan_pemantau` (implies `nti_edu_base.group_base_pengguna`), `group_tagihan_bendahara` (implies
    pemantau), `group_tagihan_admin` (implies bendahara); `base.group_system` implies `group_tagihan_admin`.
  - `nti_edu.tagihan.bulan`: `name`, `nomor` (1–12); xmlid `bulan_01`…`bulan_12`.
  - `nti_edu.tagihan.periode.jenis`: `dasar` Selection(`bulan`,`semester`,`tahun_ajaran`,`sekali`), `jumlah_bulan`
    (Integer, default 1, >0), `hari_terbit` (1–28, default 1), `hari_jatuh_tempo` (Integer, default 10),
    `bulan_libur_ids`. Data awal xmlid `periode_bulanan`, `periode_semester`, `periode_tahunan`, `periode_sekali`.
  - `nti_edu.tagihan.aturan.denda`: `tipe` (`tetap`,`persen`), `nilai` (Float >0), `berulang` (`sekali`,`per_bulan`),
    `tenggang_hari` (≥0), `maks` (Float ≥0), `komponen_denda_id` (wajib, domain `jenis='denda'`). Data awal
    `aturan_denda_contoh` (tetap 10000, per_bulan, 7 hari).
  - `nti_edu.tagihan.aturan.cicilan`: `maks_kali` (≥2), `jarak` (≥1), `jarak_satuan` (`hari`,`bulan`),
    `uang_muka_persen` (0–<100). Data awal `aturan_cicilan_4_bulanan`, `aturan_cicilan_2_per_6_bulan`.
  - `nti_edu.tagihan.aturan.masuk`: `cara` (`penuh`,`berikutnya`,`prorata`). Data awal `aturan_masuk_penuh`,
    `aturan_masuk_berikutnya`, `aturan_masuk_prorata`.
  - `nti_edu.tagihan.rekening`: `bank`, `nomor`, `atas_nama`, `company_ids`, `journal_id` (wajib, type bank/cash),
    `instruksi` (Html); method `_untuk_unit(company) -> recordset` (aktif, `company_ids` kosong atau memuat unit).
  - `nti_edu.tagihan.alasan.tolak` / `nti_edu.tagihan.alasan.hapus`: `name`, `perlu_catatan`. Data awal sesuai spec.
  - Semua master: `name`, `company_id` (opsional), `active`, `sequence`.
  - `nti_edu.tagihan.komponen`: `name`, `kode`, `company_id`, `sequence`, `active`, `jenis` (`biaya`,`denda`),
    `periode_jenis_id` (wajib bila `biaya`), `aturan_masuk_id` (default `aturan_masuk_penuh`), `aturan_cicilan_id`,
    `aturan_denda_id`, `akun_pendapatan_id` (account.account, opsional), `product_id` (service, dibuat otomatis di
    `create`, nama sinkron, `property_account_income_id` = akun pendapatan). Data awal `komponen_denda`
    ("Denda Keterlambatan", `jenis='denda'`).
  - Menu root "Keuangan Sekolah" (`menu_tagihan_root`, grup pemantau) + `menu_tagihan_konfigurasi` (grup admin) dengan
    submenu master sesuai spec §4.10.
  - `tests/common.py` `NtiTagihanCommon(NtiEduCommon)` (dari `odoo.addons.nti_edu_base.tests.common`): memuat
    `account.chart.template.try_loading('generic_coa', company=cls.yayasan, install_demo=False)`; tahun ajaran
    2026/2027 (2026-07-01 s.d. 2027-06-30, aktif) + semester ganjil (Jul–Des) & genap (Jan–Jun); rombel `rombel_7a`,
    `rombel_8a` (SMP), `rombel_10a` (SMA) dengan tingkat dari data awal base; siswa `siswa_a` (7A), `siswa_b` (8A),
    `siswa_c` (10A, adik-kakak dengan `siswa_a`: wali sama `wali_x` portal, penanggung biaya, ber-email); user
    `bendahara_smp`, `bendahara_sma`, `pemantau_smp`, `admin_keu` (yayasan+SMP+SMA), `sysadmin`
    (`base.group_system`); helper `_buat_komponen(nama, periode_xmlid, **vals)`,
    `_buat_rekening(unit)`.

- [ ] **Step 1: Tes gagal** `TestMaster`:
  - `test_grup`: `group_tagihan_admin` ⊃ bendahara ⊃ pemantau ⊃ `group_base_pengguna`; `sysadmin` ∈ admin; tidak ada
    grup tagihan yang meng-imply `account.group_account_invoice` atau `account.group_account_readonly`.
  - `test_data_awal_master`: 12 bulan; 4 periode; 3 aturan masuk; alasan tolak "Lainnya" `perlu_catatan` True.
  - `test_komponen_buat_produk`: komponen baru punya `product_id` jenis service; ganti nama → nama produk ikut;
    akun pendapatan diisi → `property_account_income_id` produk sama.
  - `test_komponen_biaya_wajib_periode`: `jenis='biaya'` tanpa periode → `ValidationError`; `jenis='denda'` boleh.
  - `test_validasi_master`: `jumlah_bulan=0`, `maks_kali=1`, `uang_muka_persen=100`, `hari_terbit=31` →
    `ValidationError`.
  - `test_hak_master`: `bendahara_smp` baca komponen/aturan OK, buat → `AccessError`; `admin_keu` buat OK.
  - `test_rekening_untuk_unit`: rekening tanpa `company_ids` dan rekening khusus SMA → `_untuk_unit(unit_smp)` hanya
    yang pertama.
- [ ] **Step 2: Jalankan** dengan `-i nti_edu_tagihan` di DB baru → gagal (modul belum ada).
- [ ] **Step 3: Implementasi** sesuai Interfaces. ACL master: pemantau baca, admin CRUD.
- [ ] **Step 4: Suite + `uji_tunggal.ps1 -Modul nti_edu_tagihan`** → `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_tagihan: kerangka modul, grup, data master biaya dan komponen`

### Task 2: Skema biaya dan potongan

**Files:**
- Create: `models/skema.py`, `models/potongan.py`, `views/skema_views.xml`, `views/potongan_views.xml`,
  `tests/test_skema_potongan.py`
- Modify: `security/ir.model.access.csv`, `security/nti_edu_tagihan_rules.xml` (baru), `views/menu.xml`,
  `__manifest__.py`

**Interfaces:**
- Consumes: Task 1 komponen/master, `NtiTagihanCommon`.
- Produces:
  - `nti_edu.tagihan.skema`: `name` (compute "<unit> <TA>"), `company_id` (unit, wajib), `tahun_ajaran_id`,
    `state` (`draft`,`aktif`,`arsip`), `baris_ids`; constraint satu `aktif` per (unit, TA);
    `_aktif_untuk(company, tahun_ajaran) -> skema`; `action_aktifkan()`, `action_arsipkan()`,
    `action_salin_tahun_berikut() -> action` (skema draft baru pada TA berikutnya menurut `tanggal_mulai`).
  - `nti_edu.tagihan.skema.baris`: `skema_id`, `komponen_id` (domain `jenis='biaya'`), `tingkat_id`, `jurusan_id`,
    `nominal` (Monetary, `currency_id` related company); SQL unique (skema, komponen, tingkat, jurusan) — kolom NULL
    diperlakukan sama lewat indeks unik `COALESCE(...,0)`.
  - `skema._baris_untuk(komponen, tingkat, jurusan) -> skema.baris` (paling spesifik: tingkat+jurusan > tingkat >
    jurusan > umum; kosong bila tidak ada).
  - `nti_edu.tagihan.potongan.jenis`: `tipe` (`persen`,`nominal`), `nilai_bawaan`, `komponen_ids`, `dapat_digabung`,
    `perlu_persetujuan`, `company_id`, `active`.
  - `nti_edu.tagihan.potongan`: `siswa_id` (domain siswa), `jenis_id`, `nilai`, `tanggal_mulai`, `tanggal_selesai`,
    `alasan`, `lampiran`, `state` (`draft`,`menunggu`,`aktif`,`berakhir`,`ditolak`), `company_id` (related siswa,
    stored); `action_ajukan()` (→ `aktif`, atau `menunggu` bila jenis `perlu_persetujuan`), `action_setujui()`,
    `action_tolak()` (keduanya admin), `action_akhiri()`.
  - `nti_edu.tagihan.potongan._hitung(siswa, komponen, tanggal, nominal) -> list[tuple(jenis, jumlah)]`
    (`@api.model`, sudo): potongan `aktif` siswa itu yang rentangnya memuat `tanggal` dan jenisnya berlaku untuk
    komponen; jumlah = `nilai%×nominal` atau `nilai`; himpunan A = semua `dapat_digabung` (dijumlah), B = satu potongan
    tidak-dapat-digabung terbesar; pakai yang totalnya lebih besar (seri → A); total dipangkas ke `nominal` (pangkas dari
    item terakhir).
  - Rule: skema/potongan `company_id in company_ids` (jenis potongan: kosong atau parent_of).
- [ ] **Step 1: Tes gagal** `TestSkemaPotongan`:
  - `test_baris_paling_spesifik`: baris umum 100.000, tingkat VII 150.000, tingkat VII+jurusan J 175.000 →
    `_baris_untuk(spp, VII, J)`=175.000, `(spp, VII, False)`=150.000, `(spp, VIII, False)`=100.000.
  - `test_baris_ganda_ditolak`: dua baris (spp, VII, kosong) di skema yang sama → `IntegrityError`/`ValidationError`.
  - `test_satu_skema_aktif`: dua skema aktif SMP 2026/2027 → `ValidationError`; SMA boleh.
  - `test_salin_tahun_berikut`: hasil draft di TA 2027/2028 dengan baris identik.
  - `test_potongan_gabung_vs_terbesar`: saudara 10% (gabung) + yatim 50.000 (gabung) + prestasi 100% (tidak gabung)
    pada nominal 200.000 → total 200.000 dari prestasi; tanpa prestasi → 20.000+50.000.
  - `test_potongan_pangkas_dan_rentang`: nominal 200.000 dengan dua potongan gabung 150.000 + 100.000 → total tepat
    200.000 (150.000 + 50.000); tanggal di luar rentang → kosong; komponen tidak termasuk → kosong.
  - `test_perlu_persetujuan`: ajukan jenis ber-persetujuan → `menunggu`, `_hitung` mengabaikan; `bendahara_smp`
    `action_setujui` → `AccessError`; `admin_keu` setujui → ikut dihitung.
  - `test_isolasi_unit`: `bendahara_sma` tidak menemukan potongan/skema SMP.
- [ ] **Step 2: Jalankan** `-u nti_edu_tagihan` → gagal.
- [ ] **Step 3: Implementasi.** ACL: pemantau baca skema/potongan; bendahara CRUD potongan (tanpa hapus yang
  `aktif`), baca skema; admin CRUD semua.
- [ ] **Step 4: Suite + uji tunggal** → lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: skema biaya per unit dan potongan siswa`

### Task 3: Tagihan di invoice, pengaturan unit, dan cakupan akses pembukuan

**Files:**
- Create: `models/account_move.py`, `models/account_payment.py`, `models/res_company.py`, `models/akses.py`
  (mixin penjaga), `views/tagihan_views.xml`, `views/pengaturan_views.xml`, `tests/test_tagihan_dasar.py`,
  `tests/test_akses_pembukuan.py`
- Modify: `security/ir.model.access.csv`, `security/nti_edu_tagihan_rules.xml`, `views/menu.xml`

**Interfaces:**
- Consumes: Task 1–2.
- Produces:
  - `res.company`: `nti_edu_tagihan_otomatis` (Bool), `nti_edu_tagihan_mulai` (Date), `nti_edu_denda_saldo_awal`
    (Bool), `nti_edu_tagihan_jurnal_id` (journal sale), `nti_edu_email_tagihan_terbit` (Bool, default True),
    `nti_edu_pengingat_hari` (Int, 3), `nti_edu_pengingat_tunggakan` (Int, 0), `nti_edu_denda_hapus_perlu_admin`
    (Bool, True), `nti_edu_wali_kelas_lihat_tunggakan` (Bool, False), `nti_edu_bukti_ukuran_maks_mb` (Int, 5),
    `nti_edu_akses_pembukuan` (`dokumen_sekolah` default, `semua`). `write` menolak perubahan field ini bila bukan
    `base.group_system`/su; constraint: `tagihan_otomatis` butuh `tagihan_mulai`. `_nti_edu_jurnal_tagihan() ->
    account.journal` (field atau jurnal sale pertama yang berlaku untuk company).
  - Mixin `nti_edu.tagihan.akses` (AbstractModel): `_nti_edu_cek_hak(grup_xmlid, companies)` → `AccessError` bila
    user bukan anggota grup atau salah satu company ∉ `env.user.company_ids` (su lolos).
  - `account.move`: `nti_edu_siswa_id` (M2o res.partner biasa, diisi `_nti_edu_terbitkan` = partner invoice),
    `nti_edu_komponen_id`, `nti_edu_periode` (Date), `nti_edu_tahun_ajaran_id`,
    `nti_edu_semester_id`, `nti_edu_rombel_id`, `nti_edu_tagihan_asal_id`, `nti_edu_denda_jatuh_tempo` (Date),
    `nti_edu_denda_bulan_ke` (Int), `nti_edu_saldo_awal` (Bool), `nti_edu_sumber` (Char `model,id`),
    `nti_edu_potongan_id` (M2o potongan, untuk nota kredit potongan). Indeks unik parsial (di `init`, semua
    `WHERE state != 'cancel'`): (a) `(nti_edu_siswa_id, nti_edu_komponen_id, nti_edu_periode)` untuk out_invoice
    tanpa sumber/asal dengan periode; (b) `(nti_edu_siswa_id, nti_edu_komponen_id)` untuk out_invoice tanpa
    sumber/asal/periode; (c) `(nti_edu_sumber)` bila terisi; (d) `(nti_edu_tagihan_asal_id, nti_edu_denda_jatuh_tempo,
    nti_edu_denda_bulan_ke)` bila asal terisi; (e) `(nti_edu_potongan_id, reversed_entry_id)` bila potongan terisi.
  - `account.move._nti_edu_terbitkan(siswa, komponen, nominal, tanggal, jatuh_tempo, potongan=(), **sekolah) ->
    account.move` (`@api.model`, sudo): out_invoice posted, partner = siswa, company = `siswa.company_id`, jurnal
    `_nti_edu_jurnal_tagihan()`, baris 1 produk komponen × nominal, satu baris negatif per `(jenis, jumlah)` bernama
    "Potongan <jenis>"; `sekolah` = nilai field `nti_edu_*` tanpa awalan (`periode`, `tahun_ajaran_id`, `semester_id`,
    `rombel_id`, `tagihan_asal_id`, `denda_jatuh_tempo`, `denda_bulan_ke`, `saldo_awal`, `sumber`); pelanggaran indeks
    → `UserError` ramah ("Tagihan ini sudah ada"). Wajib `siswa.nti_edu_is_siswa`.
  - `account.move._nti_edu_buat_tagihan(siswa, komponen, nominal, sumber, keterangan=None) -> account.move`
    (API jembatan; `sumber` = record; tanpa skema/potongan; jatuh tempo = hari ini + `hari_jatuh_tempo` periode
    komponen atau 0).
  - `account.move`: `nti_edu_lunas` (compute: `amount_residual == 0` dan posted), `nti_edu_is_tagihan` (stored,
    `bool(nti_edu_komponen_id)`).
  - `account.payment`: `nti_edu_dari_tagihan` (Bool).
  - Rule grup pemantau (dan turunannya) pada `account.move`: `['|', ('company_id.nti_edu_akses_pembukuan', '=',
    'semua'), '|', ('nti_edu_is_tagihan', '=', True), ('origin_payment_id.nti_edu_dari_tagihan', '=', True)]`;
    `account.move.line` sama lewat `move_id.`; `account.payment`: `['|', (company semua), ('nti_edu_dari_tagihan',
    '=', True)]`. ACL baca (tanpa tulis) grup pemantau untuk model akuntansi yang dibaca view/laporan modul
    (`account.move`, `.line`, `account.payment`, `account.journal`, `account.partial.reconcile`,
    `account.full.reconcile`, `account.payment.term`, `account.payment.term.line`, `account.tax`, dsb. seperlunya).
  - Menu "Tagihan" (list/form invoice sendiri: siswa, komponen, periode, rombel, total, sisa, jatuh tempo, status),
    "Pembayaran", "Konfigurasi › Pengaturan" (list/form `res.company` unit: field di atas; readonly bagi non-system).
- [ ] **Step 1: Tes gagal** `TestTagihanDasar`:
  - `test_terbitkan`: `_nti_edu_terbitkan(siswa_a, spp, 200000, ...)` dengan potongan `[(saudara, 20000)]` → posted,
    partner siswa, company SMP, 2 baris, `amount_total` 180.000, field sekolah terisi.
  - `test_cegah_ganda`: terbitkan dua kali (siswa, spp, 2026-08-01) → kedua `UserError`; setelah yang pertama dibatalkan
    → boleh lagi; komponen periode sekali dua kali → `UserError`.
  - `test_nol_langsung_lunas`: nominal 200.000 potongan 200.000 → `nti_edu_lunas` True.
  - `test_api_jembatan`: dua tagihan sumber berbeda (komponen & siswa sama) boleh; sumber sama dua kali → `UserError`;
    partner bukan siswa → `UserError`.
  - `test_pengaturan_hanya_admin_sistem`: `admin_keu` menulis `nti_edu_akses_pembukuan` → `AccessError`; `sysadmin`
    OK; `tagihan_otomatis=True` tanpa `tagihan_mulai` → `ValidationError`.
  `TestAksesPembukuan`:
  - `test_mode_bawaan`: tagihan siswa SMP + tagihan vendor SMP (in_invoice dibuat su) → `bendahara_smp` &
    `pemantau_smp` hanya menemukan tagihan siswa (`search` dan `browse().read()` vendor → `AccessError`).
  - `test_mode_semua`: `unit_smp.nti_edu_akses_pembukuan='semua'` → keduanya terlihat; tagihan SMA tetap tidak.
  - `test_akuntan_selalu_semua`: user `account.group_account_invoice` + `group_tagihan_bendahara` di SMP melihat tagihan
    vendor pada mode bawaan.
  - `test_bendahara_tidak_tulis_langsung`: `bendahara_smp` `write`/`create` `account.move` → `AccessError`.
- [ ] **Step 2: Jalankan** → gagal.
- [ ] **Step 3: Implementasi.**
- [ ] **Step 4: Suite + uji tunggal** → lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: tagihan berbasis invoice, pengaturan unit, cakupan akses pembukuan`

### Task 4: Mesin pembuatan tagihan, jadwal harian, wizard Buat Tagihan

**Files:**
- Create: `models/mesin.py`, `wizard/__init__.py`, `wizard/buat_tagihan.py`, `wizard/buat_tagihan_views.xml`,
  `data/cron.xml`, `tests/test_mesin.py`

**Interfaces:**
- Consumes: Task 2 (`_aktif_untuk`, `_baris_untuk`, `potongan._hitung`), Task 3 (`_nti_edu_terbitkan`), base
  (`_nti_edu_rombel_pada`, keanggotaan `nti_edu.rombel.anggota`).
- Produces (`nti_edu.tagihan.mesin`, AbstractModel, sudo):
  - `_periode_dalam_tahun(komponen, tahun_ajaran) -> list[dict(periode, akhir, terbit, jatuh_tempo, semester)]`:
    `bulan` → tiap `jumlah_bulan` bulan dari bulan `tanggal_mulai` TA s.d. `tanggal_selesai`, lewati bulan libur
    (periode yang bulan pertamanya libur); `semester` → semester TA; `tahun_ajaran` → satu; `sekali` → satu dengan
    `periode=False`. `terbit` = tanggal `hari_terbit` bulan pertama periode; `jatuh_tempo` = tanggal
    `hari_jatuh_tempo` bulan pertama (dipangkas ke akhir bulan) atau, untuk `sekali`, `terbit + hari_jatuh_tempo`.
  - `_rencana(company, komponen, info, rombel=None) -> dict(buat=list[dict(siswa, rombel, nominal, potongan)],
    lewati=list[tuple(siswa, alasan)])`: siswa `nti_edu_status='aktif'` dengan keanggotaan rombel di `company`
    (dan `rombel` bila diberikan) yang beririsan dengan [periode, akhir]; rombel = `_nti_edu_rombel_pada(max(periode,
    tanggal_masuk))`; nominal dari baris skema aktif (TA info) untuk tingkat/jurusan rombel — tanpa baris → tidak
    ditagih (bukan "lewati"); masuk tengah (tanggal masuk > periode, periode >1 bulan): `penuh` / `berikutnya` (tidak
    ditagih) / `prorata` (nominal × bulan tersisa termasuk bulan masuk ÷ jumlah bulan periode, dibulatkan mata
    uang); periode < `company.nti_edu_tagihan_mulai` → tidak ditagih; `sekali`: tidak ditagih bila keanggotaan
    pertama siswa di unit itu dimulai sebelum `tagihan_mulai` (tanggal masuk kosong = sebelum); sudah ada tagihan
    → `lewati` ("sudah ditagih"); potongan = `potongan._hitung(siswa, komponen, periode atau terbit, nominal)`.
  - `_terbitkan(company, komponen, info, rombel=None) -> dict(buat=account.move, lewati=list)`: tiap siswa dalam
    savepoint sendiri; galat satu siswa dicatat di `lewati`, tidak menghentikan yang lain.
  - `_cron_buat_tagihan(hari_ini=None)`: untuk unit `nti_edu_tagihan_otomatis`, TA aktif, setiap komponen `biaya`
    di skema aktif, setiap periode yang `terbit <= hari_ini` → `_terbitkan`. Cron xmlid `cron_buat_tagihan` (harian).
  - Wizard `nti_edu.tagihan.buat.wizard`: `company_id` (default company aktif), `komponen_id`, `tahun_ajaran_id`
    (default aktif), `periode` (Date, harus salah satu periode `_periode_dalam_tahun`; untuk `sekali` kosong),
    `rombel_ids`, compute `jumlah_siswa`, `total`, `daftar_lewati` (Text); `action_terbitkan()` (cek
    `group_tagihan_bendahara` + unit) → notifikasi jumlah terbit & dilewati.
- [ ] **Step 1: Tes gagal** `TestMesin` (freeze_time bila perlu):
  - `test_periode_bulanan_libur`: bulanan dengan Juni libur pada TA 2026/2027 → 11 periode, Jul 2026 … Mei 2027;
    triwulan (`jumlah_bulan=3`) → 4 periode (Jul, Okt, Jan, Apr).
  - `test_jatuh_tempo_dipangkas`: `hari_jatuh_tempo=31` → Feb 2027 = 2027-02-28.
  - `test_siswa_masuk_tengah_bulanan`: anggota masuk 2026-09-15 → tagihan Sep dibuat, Agu tidak.
  - `test_masuk_tengah_semester`: masuk 2026-10-01, semester ganjil 600.000: penuh → 600.000; berikutnya → tidak ada;
    prorata → 300.000 (3 dari 6 bulan).
  - `test_tagihan_mulai`: `tagihan_mulai` 2026-11-01 → cron pada 2026-11-02 menerbitkan hanya Nov; uang pangkal
    (sekali) tidak untuk siswa yang masuk 2026-07-01, ya untuk siswa masuk 2026-11-05.
  - `test_cron_idempoten`: cron dua kali pada hari yang sama → jumlah tagihan sama; satu siswa yang memicu galat (mis.
    tanpa skema yang cocok karena baris dihapus di tengah) tidak menghentikan siswa lain.
  - `test_siswa_nonaktif_dilewati`: `siswa_b` status `pindah` → tidak ditagih; tagihan lama tetap.
  - `test_tingkat_berbeda`: skema VII 150.000 / VIII 175.000 → `siswa_a` 150.000, `siswa_b` 175.000.
  - `test_wizard_pratinjau_dan_lewati`: wizard SPP Agustus rombel 7A → `jumlah_siswa`=1; setelah terbit, wizard sama →
    0 dibuat, `daftar_lewati` memuat `siswa_a`; `pemantau_smp` `action_terbitkan` → `AccessError`; `bendahara_sma`
    untuk SMP → `AccessError`.
  - `test_potongan_diterapkan`: potongan saudara 10% aktif → tagihan SPP 200.000 punya baris −20.000.
- [ ] **Step 2: Jalankan** → gagal.
- [ ] **Step 3: Implementasi.**
- [ ] **Step 4: Suite + uji tunggal** → lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: mesin pembuatan tagihan, jadwal harian, wizard buat tagihan`

### Task 5: Koreksi tagihan — batal, tunggakan awal, potongan mundur

**Files:**
- Create: `wizard/batal_tagihan.py`, `wizard/saldo_awal.py`, views wizard terkait, `tests/test_koreksi.py`
- Modify: `models/potongan.py`, `models/account_move.py`, `views/potongan_views.xml`, `views/tagihan_views.xml`

**Interfaces:**
- Consumes: Task 3 `_nti_edu_terbitkan`, Task 2 `_hitung`.
- Produces:
  - Wizard `nti_edu.tagihan.batal.wizard` (`tagihan_ids`, `alasan` wajib) `action_batal()`: bendahara unit; hanya
    tagihan tanpa pembayaran (`amount_residual == amount_total`), selain itu `UserError` "gunakan nota kredit";
    sudo `button_draft()` + `button_cancel()`; alasan ke chatter.
  - Wizard `nti_edu.tagihan.saldo.awal.wizard` + baris (`siswa_id`, `komponen_id`, `periode` (Date), `jatuh_tempo`,
    `nominal`) `action_simpan()` → `_nti_edu_terbitkan(..., saldo_awal=True)`; bendahara/admin unit siswa.
  - `potongan.action_terapkan_terbit()`: untuk tagihan posted siswa itu, komponen ∈ jenis, periode (atau tanggal
    invoice bila tanpa periode) dalam rentang, `amount_residual > 0`, belum punya nota kredit potongan ini → nota
    kredit (`out_refund`, `reversed_entry_id` = tagihan, `nti_edu_potongan_id`, `nti_edu_komponen_id`) sebesar
    `min(potongan_baru − potongan_yang_sudah_ada_di_tagihan, residual)` bila > 0, posted dan direkonsiliasi dengan
    tagihan; ringkasan ke chatter potongan & tagihan. Hanya potongan `aktif`.
- [ ] **Step 1: Tes gagal** `TestKoreksi`:
  - `test_batal_belum_bayar`: batal → `state='cancel'`, alasan di chatter; tagihan yang sama bisa diterbitkan ulang.
  - `test_batal_sudah_bayar_ditolak`: tagihan dibayar sebagian (lewat su) → `UserError`.
  - `test_saldo_awal`: dua baris → tagihan `nti_edu_saldo_awal` True; baris duplikat → `UserError` untuk baris itu.
  - `test_potongan_mundur`: SPP Agu & Sep 200.000 sudah terbit tanpa potongan, Agu sudah lunas; prestasi 100% mulai
    2026-08-01 disetujui → tagihan Agu & Sep tidak berubah sebelum tombol; setelah `action_terapkan_terbit` → Sep
    sisa 0 lewat nota kredit 200.000, Agu tidak disentuh; tombol kedua kali tidak membuat nota kredit baru.
- [ ] **Step 2–4:** jalankan gagal → implementasi → suite + uji tunggal lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: batal tagihan, tunggakan awal, potongan mundur lewat nota kredit`

### Task 6: Pembayaran langsung, alokasi, saldo kredit

**Files:**
- Create: `models/pembayaran.py` (metode alokasi di mesin atau model terpisah), `wizard/terima_pembayaran.py`,
  `wizard/terima_pembayaran_views.xml`, `report/kuitansi.xml`, `tests/test_pembayaran.py`
- Modify: `models/account_move.py`, `views/tagihan_views.xml`

**Interfaces:**
- Consumes: Task 1 rekening, Task 3 tagihan.
- Produces:
  - `nti_edu.tagihan.mesin._bayar(tagihan, jumlah, rekening, tanggal, memo, siswa_kelebihan=None) ->
    account.payment` (sudo): semua tagihan harus satu company & posted; alokasi urut `invoice_date_due` (lalu id)
    hanya ke `amount_residual`; per siswa satu payment via `account.payment.register` (`active_model='account.move.line'`,
    baris piutang tagihan siswa itu, `amount` = alokasi, `journal_id` = `rekening.journal_id`, `group_payment=True`,
    `payment_difference_handling='open'`), `nti_edu_dari_tagihan=True`; kelebihan (`jumlah − total sisa`) ditambahkan
    ke payment siswa `siswa_kelebihan` (bawaan siswa pertama menurut nama) sehingga menjadi kredit tak terpakai.
  - `res.partner.nti_edu_saldo_kredit` (compute, groups pemantau): jumlah sisa kredit (baris piutang kredit belum
    direkonsiliasi) siswa.
  - Wizard `nti_edu.tagihan.bayar.wizard`: `siswa_id`, `tagihan_ids` (default semua tagihan terbuka siswa, urut jatuh
    tempo), `nominal`, `rekening_id` (domain `_untuk_unit`), `tanggal`; `action_bayar()` (bendahara unit) → `_bayar`
    lalu kembalikan aksi cetak kuitansi (`account.action_report_payment_receipt` atau salinan berkop unit).
  - Tombol "Terapkan Kredit" di tagihan (bendahara): sudo `js_assign_outstanding_line` untuk kredit siswa yang sama.
- [ ] **Step 1: Tes gagal** `TestPembayaran`:
  - `test_alokasi_jatuh_tempo_terlama`: tagihan Agu 200.000 & Sep 200.000, bayar 300.000 → Agu lunas, Sep sisa
    100.000.
  - `test_kelebihan_jadi_kredit`: bayar 500.000 untuk 400.000 → keduanya lunas, `nti_edu_saldo_kredit` = 100.000;
    tagihan Okt baru + "Terapkan Kredit" → sisa Okt 100.000.
  - `test_dua_saudara_satu_unit`: tagihan siswa_a & adik di SMP (buat siswa SMP kedua) → dua payment, masing-masing
    partner siswanya.
  - `test_beda_unit_ditolak`: tagihan SMP + SMA dalam satu `_bayar` → `UserError`.
  - `test_hak`: `pemantau_smp` `action_bayar` → `AccessError`; `bendahara_smp` OK dan payment terbaca olehnya pada
    mode bawaan.
- [ ] **Step 2–4:** gagal → implementasi → suite + uji tunggal lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: terima pembayaran, alokasi jatuh tempo, saldo kredit dan kuitansi`

### Task 7: Konfirmasi transfer (backend) dan email

**Files:**
- Create: `models/konfirmasi.py`, `wizard/tolak_konfirmasi.py`, views terkait, `data/mail_template.xml`,
  `data/sequence.xml`, `tests/test_konfirmasi.py`
- Modify: `security/*`, `views/menu.xml`, `models/account_move.py`, `nti_edu_base/models/res_users.py`,
  `nti_edu_base/tests/test_akses.py`

**Interfaces:**
- Consumes: Task 6 `_bayar`, Task 1 alasan tolak & rekening.
- Produces:
  - Base: `res.users._nti_edu_siswa_portal(termasuk_nonaktif=False)`; bila True juga siswa yang status-nya bukan
    `aktif` atau diarsipkan (tetap hanya yang terhubung lewat baris wali / dirinya). Perilaku bawaan tidak berubah.
    Tes base `test_helper_termasuk_nonaktif`: wali dengan anak `lulus` → bawaan tidak memuat, `True` memuat.
  - `nti_edu.tagihan.konfirmasi` (`mail.thread`): `name` (sequence `KT/%(year)s/`), `pengirim_id` (res.partner),
    `company_id`, `tagihan_ids` (M2m account.move), `siswa_ids` (compute stored), `tanggal_transfer`, `nominal`,
    `nominal_diterima`, `rekening_id`, `nama_rekening_pengirim`, `bukti` (Binary attachment), `bukti_nama`, `catatan`,
    `state` (`menunggu`,`diterima`,`ditolak`), `alasan_tolak_id`, `catatan_tolak`, `payment_ids`,
    `diverifikasi_oleh_id`, `tanggal_verifikasi`.
  - `konfirmasi._buat_dari_portal(user, tagihan_ids, vals) -> konfirmasi` (`@api.model`, sudo): tagihan harus posted,
    belum lunas, siswanya ∈ `user._nti_edu_siswa_portal(termasuk_nonaktif=True)`, satu company; bukti wajib, ekstensi jpg/jpeg/png/pdf, ukuran ≤ `nti_edu_bukti_ukuran_maks_mb`;
    rekening ∈ `_untuk_unit`; selain itu `UserError`.
  - `action_terima()` (bendahara unit, state `menunggu`): `_bayar(tagihan terbuka, nominal_diterima or nominal,
    rekening, tanggal_transfer, name)`; set state/verifikator; email `mail_template_konfirmasi_diterima`.
  - Wizard `nti_edu.tagihan.tolak.wizard` (`konfirmasi_id`, `alasan_id`, `catatan`; catatan wajib bila
    `perlu_catatan`) → state `ditolak`, email `mail_template_konfirmasi_ditolak`. Konfirmasi non-`menunggu` tidak bisa
    diubah (write guard kecuali lewat aksi).
  - `account.move.nti_edu_menunggu_verifikasi` (compute: ada konfirmasi `menunggu` memuatnya).
  - `res.partner._nti_edu_penerima_tagihan() -> res.partner` (siswa → wali `is_penanggung_biaya` ber-email; bila
    tidak ada, wali `is_kontak_utama` ber-email; bila tidak ada, kosong).
  - Menu "Konfirmasi Transfer" (filter bawaan `menunggu`, pratinjau bukti di form).
- [ ] **Step 1: Tes gagal** `TestKonfirmasi`:
  - `test_buat_valid_dan_terima`: `wali_x` mengirim untuk SPP `siswa_a` 200.000 → `menunggu`, tagihan
    `nti_edu_menunggu_verifikasi`; `bendahara_smp` terima → payment, tagihan lunas, email diterima ke `wali_x`
    (`mail.mail` terbentuk).
  - `test_terima_nominal_dikoreksi`: lapor 200.000, `nominal_diterima` 150.000 → sisa 50.000.
  - `test_tagihan_dibayar_tunai_sebelum_verifikasi`: tagihan lunas tunai lalu konfirmasi diterima → seluruh nominal
    menjadi saldo kredit.
  - `test_tolak`: alasan "Lainnya" tanpa catatan → `UserError`; dengan catatan → `ditolak`, email; `write` nominal
    setelahnya → `UserError`.
  - `test_server_menolak`: tagihan siswa lain (bukan anak `wali_x`) → `UserError`; tagihan SMP + SMA (anak `wali_x`
    lintas unit) → `UserError`; berkas `.exe` atau > batas → `UserError`.
  - `test_isolasi`: `bendahara_sma` tidak menemukan konfirmasi SMP dan `action_terima` → `AccessError`.
- [ ] **Step 2–4:** gagal → implementasi → suite `/nti_edu_tagihan`, `/nti_edu_base`, `/nti_edu_pegawai` + uji
  tunggal tagihan & base lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: konfirmasi transfer, verifikasi bendahara dan email` (perubahan helper
  base ikut commit ini; sebutkan di pesan).

### Task 8: Cicilan

**Files:**
- Create: `wizard/cicilan.py`, `wizard/cicilan_views.xml`, `tests/test_cicilan.py`
- Modify: `models/account_move.py`, `views/tagihan_views.xml`

**Interfaces:**
- Consumes: Task 1 aturan cicilan, Task 3 tagihan.
- Produces:
  - `account.move._nti_edu_atur_cicilan(jumlah_kali) -> None` (sudo setelah cek bendahara unit): syarat komponen punya
    `aturan_cicilan_id`, `2 ≤ jumlah_kali ≤ maks_kali`, belum ada pembayaran, bukan denda; `button_draft()`, set
    `invoice_payment_term_id` ke termin hasil `_nti_edu_termin_cicilan(...)`, `action_post()`; riwayat di chatter.
  - Jadwal cicilan: jatuh tempo ke-i = `invoice_date_due` awal + i×`jarak` (`hari` → hari, `bulan` →
    `relativedelta(months=)`), i = 0..n−1; nominal: bila `uang_muka_persen` > 0 → cicilan pertama =
    round(total × persen/100), sisanya dibagi rata; selain itu dibagi rata; selisih pembulatan di cicilan terakhir.
  - `_nti_edu_termin_cicilan(tanggal_invoice, jadwal) -> account.payment.term` (dibuat/dipakai ulang; isi persis
    menghasilkan `date_maturity`/jumlah jadwal di atas).
  - Wizard `nti_edu.tagihan.cicilan.wizard` (`tagihan_id`, `jumlah_kali`, pratinjau jadwal).
- [ ] **Step 1: Tes gagal** `TestCicilan`:
  - `test_cicil_rata`: uang pangkal 1.000.000 jatuh tempo 2026-07-10, aturan 4× bulanan → baris piutang 250.000 pada
    07-10, 08-10, 09-10, 10-10.
  - `test_cicil_uang_muka`: 1.000.000, uang muka 40%, 3× → 400.000, 300.000, 300.000.
  - `test_pembulatan`: 1.000.000 3× tanpa uang muka → 333.333, 333.333, 333.334 (jumlah tepat).
  - `test_syarat`: komponen tanpa aturan, `jumlah_kali` > maks, sudah ada pembayaran → `UserError`;
    `pemantau_smp` → `AccessError`.
- [ ] **Step 2–4:** gagal → implementasi → suite + uji tunggal lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: cicilan tagihan dengan termin pembayaran`

### Task 9: Denda keterlambatan dan penghapusan denda

**Files:**
- Create: `models/denda.py` (atau di `mesin.py`), `wizard/hapus_denda.py`, views, `tests/test_denda.py`
- Modify: `data/cron.xml`

**Interfaces:**
- Consumes: Task 1 aturan denda/alasan hapus, Task 3 `_nti_edu_terbitkan`, Task 8 baris piutang per cicilan.
- Produces:
  - `nti_edu.tagihan.mesin._cron_denda(hari_ini=None)` (cron `cron_denda`, harian): untuk out_invoice posted,
    `nti_edu_is_tagihan`, bukan denda (komponen `jenis='biaya'`), komponen punya `aturan_denda_id`, bukan saldo awal
    kecuali `nti_edu_denda_saldo_awal` unit; untuk tiap baris piutang dengan `amount_residual > 0` dan
    `date_maturity >= company.nti_edu_tagihan_mulai` (bila diisi): batas_n = `date_maturity + tenggang_hari +
    (n−1) bulan`; untuk setiap n ≥ 1 dengan `batas_n < hari_ini` (n hanya 1 bila `sekali`) yang belum ada →
    jumlah = `nilai` (tetap) atau `round(nilai% × residual baris saat ini)`, dipangkas ke `maks − total denda
    non-batal tagihan asal` (lewati bila ≤ 0, `maks=0` = tanpa batas) → `_nti_edu_terbitkan(siswa,
    aturan.komponen_denda_id, jumlah, tanggal=hari_ini, jatuh_tempo=hari_ini, tagihan_asal_id=asal,
    denda_jatuh_tempo=date_maturity, denda_bulan_ke=n)`. Aturan yang dipakai = aturan komponen saat ini.
  - Wizard `nti_edu.tagihan.hapus.denda.wizard` (`tagihan_ids` denda, `alasan_id`, `catatan`): bila
    `nti_edu_denda_hapus_perlu_admin` → `group_tagihan_admin`, selain itu bendahara; hanya denda tanpa pembayaran →
    batal + chatter (alasan + catatan).
- [ ] **Step 1: Tes gagal** `TestDenda` (freeze_time):
  - `test_per_bulan_tenggang`: SPP jatuh tempo 2026-08-10, tenggang 7, 10.000/bulan → 2026-08-17: 0 denda;
    2026-08-18: 1; 2026-10-18: 3; jalan ulang hari sama tetap 3.
  - `test_sekali_dan_persen`: aturan sekali 2% sisa 150.000 → satu denda 3.000.
  - `test_maks`: per_bulan 10.000, maks 25.000 → denda 10.000, 10.000, 5.000, lalu berhenti.
  - `test_cicilan`: tagihan 4× cicilan, cicilan 1 & 2 terlambat → denda terpisah per cicilan (kunci jatuh tempo
    berbeda).
  - `test_tidak_denda`: tagihan lunas, tagihan denda itu sendiri, tagihan nol (beasiswa 100%), saldo awal (pengaturan
    mati), jatuh tempo sebelum `tagihan_mulai` → tidak didenda.
  - `test_hapus_denda`: pengaturan bawaan (perlu admin): `bendahara_smp` → `AccessError`, `admin_keu` OK (batal +
    chatter); pengaturan mati → bendahara OK; denda sudah dibayar → `UserError`.
- [ ] **Step 2–4:** gagal → implementasi → suite + uji tunggal lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: denda keterlambatan dan penghapusan denda`

### Task 10: Kartu SPP, tab Keuangan siswa, tunggakan, pengingat

**Files:**
- Create: `report/kartu_spp.xml`, `models/res_partner.py`, `models/tunggakan.py` (transient wali kelas),
  `views/siswa_views.xml`, `views/tunggakan_views.xml`, `tests/test_laporan.py`
- Modify: `models/mesin.py` (email terbit & pengingat), `data/mail_template.xml`, `data/cron.xml`, `views/menu.xml`

**Interfaces:**
- Consumes: Task 3–9.
- Produces:
  - `res.partner._nti_edu_data_kartu_spp(tahun_ajaran) -> dict` (sudo; dipanggil setelah cek akses oleh pemanggil):
    `bulanan` = list komponen periode 1-bulan × 12 bulan TA (sel: nominal, potongan, sisa, tanggal lunas, status
    `lunas`/`sebagian`/`belum`/`belum_terbit`/`libur`), `lainnya` = list tagihan non-bulanan & denda, `total_tagihan`,
    `total_bayar`, `sisa`, `saldo_kredit`.
  - Laporan `nti_edu_tagihan.action_report_kartu_spp` (QWeb PDF, model `res.partner`, TA dari konteks
    `tahun_ajaran_id` atau aktif).
  - `res.partner` (groups pemantau): `nti_edu_tagihan_ids` (compute), `nti_edu_sisa_tagihan`, `nti_edu_tunggakan`
    (lewat jatuh tempo), `nti_edu_potongan_ids`; tab "Keuangan" di form siswa base dengan tombol Kartu SPP & Terima
    Pembayaran.
  - `account.move.nti_edu_umur_tunggakan` (Selection `0_30`,`31_60`,`61_90`,`90_plus`, stored; diperbarui
    `_cron_perbarui_umur` harian dan saat pembayaran) + menu "Tunggakan" (list & pivot: unit, rombel, siswa,
    komponen, umur; domain posted, tagihan, residual > 0, jatuh tempo < hari ini).
  - `account.move.action_nti_edu_kirim_pengingat()` (bendahara): satu email per penerima
    (`_nti_edu_penerima_tagihan`) berisi daftar tunggakan anak-anaknya.
  - `nti_edu.tagihan.mesin._cron_pengingat(hari_ini=None)`: unit dengan `pengingat_hari` > 0 → email tagihan yang jatuh
    tempo tepat `hari_ini + pengingat_hari`; unit dengan `pengingat_tunggakan` > 0 → ringkasan tunggakan bila
    `(hari_ini − tanggal acuan) % N == 0` (acuan: tanggal 1 bulan berjalan). Email terbit (bila
    `nti_edu_email_tagihan_terbit`) dikirim di akhir `_terbitkan`: satu email per penerima untuk semua tagihan baru
    dalam satu jalan.
  - Transient `nti_edu.tagihan.tunggakan.wali` (`siswa_nama`, `rombel`, `komponen`, `sisa`, `jatuh_tempo`) +
    `action_buka_tunggakan_rombel()` (server action menu "Tunggakan Rombel Saya", grup `group_base_pengguna`):
    bila unit pengaturan mati atau user bukan wali kelas rombel aktif → aksi peringatan; selain itu baris dibuat
    sudo hanya untuk rombel yang `wali_kelas_id = user`, lalu buka list baca-saja.
- [ ] **Step 1: Tes gagal** `TestLaporan`:
  - `test_data_kartu`: siswa dengan SPP Jul lunas, Agu sebagian, Sep belum, Juni libur, uang pangkal dicicil, satu
    denda, kredit 50.000 → sel dan total sesuai; render PDF (`_render_qweb_pdf`) tanpa galat.
  - `test_tab_keuangan_hak`: `user_guru_smp` membaca `nti_edu_sisa_tagihan` → `AccessError`; `pemantau_smp` OK.
  - `test_umur`: jatuh tempo 45 hari lalu → `31_60`; dilunasi → keluar dari tunggakan; tagihan nol tidak muncul.
  - `test_pengingat`: `pengingat_hari=3`, jatuh tempo 2026-08-10, cron 2026-08-07 → satu `mail.mail` ke `wali_x`;
    siswa tanpa wali ber-email → tidak ada email, catatan di chatter tagihan.
  - `test_email_terbit_digest`: cron menerbitkan SPP `siswa_a` dan adiknya (SMP) → satu email ke `wali_x`.
  - `test_tunggakan_wali_kelas`: pengaturan mati → peringatan; nyala → wali kelas 7A hanya melihat siswa 7A; guru
    non-wali → peringatan.
- [ ] **Step 2–4:** gagal → implementasi → suite + uji tunggal lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: kartu SPP, tab keuangan siswa, tunggakan dan pengingat`

### Task 11: Portal tagihan dan konfirmasi transfer

**Files:**
- Create: `nti_edu_tagihan/controllers/__init__.py`, `controllers/portal.py`, `views/portal_templates.xml`,
  `tests/test_portal.py`

**Interfaces:**
- Consumes: Task 7 (`_buat_dari_portal`, helper base `termasuk_nonaktif`), Task 10 (`_nti_edu_data_kartu_spp`,
  laporan kartu).
- Produces:
  - Controller (turunan `CustomerPortal`): counter `nti_edu_tagihan_count` (jumlah tagihan terbuka anak-anak);
    `/my/tagihan` (anak aktif dari session base, `?siswa=<id>` untuk pindah); `/my/tagihan/konfirmasi` (GET form per
    unit, POST multipart → `_buat_dari_portal`); `/my/tagihan/kartu/<int:siswa_id>` (PDF, `?tahun=`);
    `/my/tagihan/invoice/<int:move_id>` (PDF invoice). Semua: siswa harus ∈ helper (`termasuk_nonaktif=True` tetapi
    nonaktif hanya bila masih punya tagihan terbuka) dan tagihan milik siswa itu, selain itu 404. Baca lewat sudo.
  - Halaman menampilkan: tagihan terbuka (status "Menunggu Verifikasi", cicilan dengan jatuh tempo per cicilan),
    riwayat lunas, total tunggakan, saldo kredit, rekening `_untuk_unit` + instruksi, daftar konfirmasi + status +
    alasan tolak.
- [ ] **Step 1: Tes gagal** `TestPortal` (`HttpCase`):
  - `test_halaman_tagihan`: login `wali_x` → `/my/tagihan` 200 memuat tagihan `siswa_a` & `siswa_c`, tidak memuat
    tagihan siswa lain; `/my` memuat kartu Tagihan.
  - `test_anak_lulus_bertunggakan`: anak `lulus` dengan tagihan terbuka tampil; tanpa tagihan terbuka tidak.
  - `test_kirim_konfirmasi`: POST valid (berkas png kecil) → konfirmasi `menunggu`; POST dengan id tagihan anak orang
    lain → tidak ada konfirmasi baru, pesan galat.
  - `test_pdf_akses`: kartu & invoice anak sendiri 200 (`application/pdf`); siswa lain 404.
  - `test_siswa_portal`: siswa ber-akun portal melihat tagihannya sendiri saja.
- [ ] **Step 2–4:** gagal → implementasi → suite + uji tunggal lulus.
- [ ] **Step 5: Commit** `nti_edu_tagihan: portal tagihan, konfirmasi transfer dan kartu SPP`

### Task 12: Data demo, uji asap browser, dokumen

**Files:**
- Create: `nti_edu_tagihan/demo/tagihan_demo.xml`, `static/tests/tours/tagihan_tour.js`, `tests/test_tour.py`
- Modify: `__manifest__.py` (demo, assets tour), `docs/superpowers/specs/2026-11-24-nti-edu-arsitektur-design.md`
  (§I.6 baris tagihan + §II.2 helper, spec §5), `docs/diagram/use-case-nti-edu.html` (modul Tagihan: aktor Admin
  Sistem, Admin Keuangan, Bendahara Unit, Pemantau, Wali Kelas, Orang Tua/Siswa portal, Cron; use case sesuai spec;
  status selesai; baris RIWAYAT; DIPERBARUI)

**Interfaces:**
- Consumes: semua task sebelumnya; demo base (unit SMP/SMA, siswa, wali portal demo).
- Produces: demo sesuai spec §4.12 (komponen SPP/Uang Pangkal/Kegiatan, skema aktif SMP & SMA beda per tingkat,
  jenis potongan, rekening "Bank Yayasan", user demo `bendahara_smp`/`admin_keuangan`, tagihan berjalan: beberapa
  lunas, satu dicicil, satu tunggakan berdenda, satu konfirmasi `menunggu` dari wali portal demo). Tagihan demo
  dibuat lewat `<function>` yang memanggil metode mesin dengan tanggal tetap, bukan record invoice mentah.
- [ ] **Step 1: Tes gagal** `TestTour` (`HttpCase`, dilewati bila Chrome tidak ada — pola base):
  tour sebagai admin: Keuangan Sekolah › Tagihan (list & form), Konfirmasi Transfer (buka, Terima), Proses › Buat
  Tagihan (pratinjau), Konfigurasi › Komponen/Skema/Aturan Denda/Pengaturan terbuka tanpa galat; tour portal wali:
  `/my/tagihan` → form konfirmasi tampil.
- [ ] **Step 2: Jalankan** di DB dengan demo (`nti_tagihan_tes` dibuat ulang `-i` tanpa `--without-demo`) → gagal.
- [ ] **Step 3: Implementasi** demo + tour; perbarui dokumen induk & diagram use case.
- [ ] **Step 4: Verifikasi penuh:** suite `/nti_edu_tagihan`, `/nti_edu_base`, `/nti_edu_pegawai`;
  `uji_tunggal.ps1` untuk `nti_edu_tagihan`, `nti_edu_base`, `nti_edu_pegawai` → semua `0 failed, 0 error(s)`.
- [ ] **Step 5: Commit** `nti_edu_tagihan: data demo, uji asap browser; docs: induk dan diagram use case`
