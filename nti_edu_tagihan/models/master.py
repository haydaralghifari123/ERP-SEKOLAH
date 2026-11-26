# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class TagihanMasterMixin(models.AbstractModel):
    """Field bersama data master konfigurasi tagihan (spec §4.2)."""
    _name = 'nti_edu.tagihan.master.mixin'
    _description = 'Master Konfigurasi Tagihan'
    _order = 'sequence, id'

    name = fields.Char(string='Nama', required=True)
    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', ondelete='cascade',
        help='Kosong = berlaku untuk semua unit.')
    active = fields.Boolean(string='Aktif', default=True)
    sequence = fields.Integer(string='Urutan', default=10)

    # Master boleh tanpa company, milik yayasan (induk), atau milik unit pemakai.
    _check_company_domain = models.check_company_domain_parent_of


class TagihanBulan(models.Model):
    _name = 'nti_edu.tagihan.bulan'
    _description = 'Bulan'
    _order = 'nomor'

    name = fields.Char(string='Nama', required=True)
    nomor = fields.Integer(string='Nomor', required=True)

    _sql_constraints = [
        ('nomor_unik', 'unique(nomor)', 'Nomor bulan sudah dipakai.'),
        ('nomor_rentang', 'CHECK(nomor BETWEEN 1 AND 12)', 'Nomor bulan harus 1 sampai 12.'),
    ]


class TagihanPeriodeJenis(models.Model):
    _name = 'nti_edu.tagihan.periode.jenis'
    _inherit = 'nti_edu.tagihan.master.mixin'
    _description = 'Periode Tagihan'

    dasar = fields.Selection([
        ('bulan', 'Kelipatan Bulan'),
        ('semester', 'Semester'),
        ('tahun_ajaran', 'Tahun Ajaran'),
        ('sekali', 'Sekali'),
    ], string='Dasar Periode', required=True, default='bulan',
        help='Kelipatan bulan dihitung dari awal tahun ajaran; semester mengikuti semester data sekolah.')
    jumlah_bulan = fields.Integer(
        string='Jumlah Bulan', default=1, help='Untuk dasar kelipatan bulan: 1 = bulanan, 3 = triwulan, dst.')
    hari_terbit = fields.Integer(
        string='Tanggal Terbit', default=1, help='Tanggal terbit tagihan dalam bulan pertama periode (1-28).')
    hari_jatuh_tempo = fields.Integer(
        string='Tanggal Jatuh Tempo', default=10,
        help='Tanggal jatuh tempo dalam bulan pertama periode; untuk dasar Sekali: jumlah hari setelah terbit.')
    bulan_libur_ids = fields.Many2many(
        'nti_edu.tagihan.bulan', string='Bulan Tidak Ditagih',
        help='Untuk dasar kelipatan bulan: bulan yang tidak ditagih, mis. Juni.')

    @api.constrains('jumlah_bulan', 'hari_terbit', 'hari_jatuh_tempo', 'dasar')
    def _cek_angka(self):
        for rec in self:
            if rec.jumlah_bulan <= 0:
                raise ValidationError(_('Jumlah bulan periode "%s" harus lebih dari 0.', rec.name))
            if not 1 <= rec.hari_terbit <= 28:
                raise ValidationError(_('Tanggal terbit periode "%s" harus 1 sampai 28.', rec.name))
            if rec.dasar == 'sekali':
                if rec.hari_jatuh_tempo < 0:
                    raise ValidationError(_('Jumlah hari jatuh tempo periode "%s" tidak boleh negatif.', rec.name))
            elif not 1 <= rec.hari_jatuh_tempo <= 28:
                raise ValidationError(_('Tanggal jatuh tempo periode "%s" harus 1 sampai 28.', rec.name))


class TagihanAturanDenda(models.Model):
    _name = 'nti_edu.tagihan.aturan.denda'
    _inherit = 'nti_edu.tagihan.master.mixin'
    _description = 'Aturan Denda'
    _check_company_auto = True

    tipe = fields.Selection([
        ('tetap', 'Nominal Tetap'),
        ('persen', 'Persen dari Sisa'),
    ], string='Tipe', required=True, default='tetap',
        help='Persen dihitung dari sisa tagihan atau sisa cicilan yang terlambat.')
    nilai = fields.Float(string='Nilai', required=True)
    berulang = fields.Selection([
        ('sekali', 'Sekali'),
        ('per_bulan', 'Per Bulan Keterlambatan'),
    ], string='Berulang', required=True, default='sekali')
    tenggang_hari = fields.Integer(string='Tenggang (Hari)', default=0)
    maks = fields.Float(string='Maksimum per Tagihan', default=0.0, help='0 = tanpa batas.')
    komponen_denda_id = fields.Many2one(
        'nti_edu.tagihan.komponen', string='Komponen Denda', required=True, ondelete='restrict',
        domain="[('jenis', '=', 'denda')]", check_company=True,
        help='Komponen jenis denda yang dipakai untuk menagih denda.')

    @api.constrains('nilai', 'tenggang_hari', 'maks')
    def _cek_angka(self):
        for rec in self:
            if rec.nilai <= 0:
                raise ValidationError(_('Nilai aturan denda "%s" harus lebih dari 0.', rec.name))
            if rec.tenggang_hari < 0:
                raise ValidationError(_('Tenggang aturan denda "%s" tidak boleh negatif.', rec.name))
            if rec.maks < 0:
                raise ValidationError(_('Maksimum aturan denda "%s" tidak boleh negatif.', rec.name))

    @api.constrains('komponen_denda_id')
    def _cek_komponen_denda(self):
        for rec in self:
            if rec.komponen_denda_id.jenis != 'denda':
                raise ValidationError(_(
                    'Komponen "%(komponen)s" pada aturan denda "%(aturan)s" harus berjenis denda.',
                    komponen=rec.komponen_denda_id.name, aturan=rec.name))


class TagihanAturanCicilan(models.Model):
    _name = 'nti_edu.tagihan.aturan.cicilan'
    _inherit = 'nti_edu.tagihan.master.mixin'
    _description = 'Aturan Cicilan'

    maks_kali = fields.Integer(string='Maksimum Cicilan', required=True, default=2)
    jarak = fields.Integer(string='Jarak', required=True, default=1)
    jarak_satuan = fields.Selection([
        ('hari', 'Hari'),
        ('bulan', 'Bulan'),
    ], string='Satuan Jarak', required=True, default='bulan')
    uang_muka_persen = fields.Float(
        string='Uang Muka (%)', default=0.0,
        help='0 = tanpa uang muka; bila diisi, cicilan pertama minimal sebesar persen ini.')

    @api.constrains('maks_kali', 'jarak', 'uang_muka_persen')
    def _cek_angka(self):
        for rec in self:
            if rec.maks_kali < 2:
                raise ValidationError(_('Maksimum cicilan pada aturan "%s" minimal 2 kali.', rec.name))
            if rec.jarak < 1:
                raise ValidationError(_('Jarak cicilan pada aturan "%s" minimal 1.', rec.name))
            if not 0 <= rec.uang_muka_persen < 100:
                raise ValidationError(_(
                    'Uang muka pada aturan cicilan "%s" harus 0 sampai kurang dari 100 persen.', rec.name))


class TagihanAturanMasuk(models.Model):
    _name = 'nti_edu.tagihan.aturan.masuk'
    _inherit = 'nti_edu.tagihan.master.mixin'
    _description = 'Aturan Siswa Masuk Tengah'

    cara = fields.Selection([
        ('penuh', 'Tagih Penuh'),
        ('berikutnya', 'Mulai Periode Berikutnya'),
        ('prorata', 'Prorata per Bulan'),
    ], string='Cara', required=True, default='penuh',
        help='Prorata: dibagi per bulan tersisa dalam periode, dibulatkan ke rupiah.')


class TagihanRekening(models.Model):
    _name = 'nti_edu.tagihan.rekening'
    _inherit = 'nti_edu.tagihan.master.mixin'
    _description = 'Rekening Pembayaran'

    bank = fields.Char(string='Bank', required=True)
    nomor = fields.Char(string='Nomor Rekening', required=True)
    atas_nama = fields.Char(string='Atas Nama', required=True)
    company_ids = fields.Many2many(
        'res.company', string='Unit Pemakai', help='Kosong = dipakai semua unit.')
    journal_id = fields.Many2one(
        'account.journal', string='Jurnal', required=True, ondelete='restrict',
        domain="[('type', 'in', ('bank', 'cash'))]",
        help='Jurnal bank/kas tempat pembayaran ke rekening ini dicatat (biasanya jurnal yayasan).')
    instruksi = fields.Html(string='Instruksi Transfer')

    @api.constrains('journal_id', 'company_id', 'company_ids')
    def _cek_jurnal(self):
        for rec in self:
            jurnal = rec.journal_id.sudo()
            if jurnal.type not in ('bank', 'cash'):
                raise ValidationError(_('Jurnal rekening "%s" harus jurnal bank atau kas.', rec.name))
            # Jurnal harus milik unit pemakai atau induknya (yayasan); rekening tanpa unit bebas memilih.
            for company in (rec.company_id | rec.company_ids).sudo():
                if jurnal.company_id not in company.parent_ids:
                    raise ValidationError(_(
                        'Jurnal "%(jurnal)s" pada rekening "%(rekening)s" tidak bisa dipakai unit %(unit)s.',
                        jurnal=jurnal.name, rekening=rec.name, unit=company.name))

    @api.model
    def _untuk_unit(self, company):
        """Rekening aktif yang boleh dipakai unit `company`."""
        return self.search([
            '|', ('company_ids', '=', False), ('company_ids', 'in', company.ids),
            '|', ('company_id', '=', False), ('company_id', 'parent_of', company.ids),
        ])


class TagihanAlasanTolak(models.Model):
    _name = 'nti_edu.tagihan.alasan.tolak'
    _inherit = 'nti_edu.tagihan.master.mixin'
    _description = 'Alasan Penolakan Transfer'

    perlu_catatan = fields.Boolean(string='Perlu Catatan', help='Catatan bebas wajib diisi bila alasan ini dipilih.')


class TagihanAlasanHapus(models.Model):
    _name = 'nti_edu.tagihan.alasan.hapus'
    _inherit = 'nti_edu.tagihan.master.mixin'
    _description = 'Alasan Penghapusan Denda'

    perlu_catatan = fields.Boolean(string='Perlu Catatan', help='Catatan bebas wajib diisi bila alasan ini dipilih.')
