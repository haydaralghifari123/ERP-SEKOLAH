# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class TagihanSkema(models.Model):
    _name = 'nti_edu.tagihan.skema'
    _description = 'Skema Biaya'
    _order = 'tahun_ajaran_id desc, company_id'
    _check_company_auto = True

    name = fields.Char(string='Nama', compute='_compute_name', store=True)
    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', required=True, index=True, ondelete='restrict')
    tahun_ajaran_id = fields.Many2one(
        'nti_edu.tahun.ajaran', string='Tahun Ajaran', required=True, index=True, ondelete='restrict')
    state = fields.Selection([
        ('draft', 'Draf'),
        ('aktif', 'Aktif'),
        ('arsip', 'Arsip'),
    ], string='Status', required=True, default='draft', copy=False)
    baris_ids = fields.One2many('nti_edu.tagihan.skema.baris', 'skema_id', string='Baris Biaya', copy=True)

    @api.depends('company_id.name', 'tahun_ajaran_id.name')
    def _compute_name(self):
        for rec in self:
            rec.name = ' '.join(filter(None, (rec.company_id.name, rec.tahun_ajaran_id.name))) or _('Skema Biaya')

    @api.constrains('state', 'company_id', 'tahun_ajaran_id')
    def _cek_satu_aktif(self):
        for rec in self.filtered(lambda r: r.state == 'aktif'):
            lain = self.sudo().search_count([
                ('id', '!=', rec.id), ('state', '=', 'aktif'),
                ('company_id', '=', rec.company_id.id), ('tahun_ajaran_id', '=', rec.tahun_ajaran_id.id)])
            if lain:
                raise ValidationError(_(
                    'Sudah ada skema biaya aktif untuk %(unit)s tahun ajaran %(ta)s. Arsipkan dulu skema lama.',
                    unit=rec.company_id.name, ta=rec.tahun_ajaran_id.name))

    @api.model
    def _aktif_untuk(self, company, tahun_ajaran):
        """Skema aktif unit `company` pada `tahun_ajaran` (kosong bila belum ada)."""
        return self.search([
            ('state', '=', 'aktif'), ('company_id', '=', company.id),
            ('tahun_ajaran_id', '=', tahun_ajaran.id)], limit=1)

    def action_aktifkan(self):
        self.write({'state': 'aktif'})

    def action_arsipkan(self):
        self.write({'state': 'arsip'})

    def action_salin_tahun_berikut(self):
        """Salin skema ini (beserta barisnya) menjadi draf pada tahun ajaran berikutnya."""
        self.ensure_one()
        berikut = self.env['nti_edu.tahun.ajaran'].search([
            ('tanggal_mulai', '>', self.tahun_ajaran_id.tanggal_mulai)], order='tanggal_mulai', limit=1)
        if not berikut:
            raise ValidationError(_(
                'Belum ada tahun ajaran sesudah %s. Buat tahun ajaran berikutnya terlebih dahulu.',
                self.tahun_ajaran_id.name))
        baru = self.create({
            'company_id': self.company_id.id,
            'tahun_ajaran_id': berikut.id,
            'baris_ids': [Command.create({
                'komponen_id': b.komponen_id.id, 'tingkat_id': b.tingkat_id.id,
                'jurusan_id': b.jurusan_id.id, 'nominal': b.nominal}) for b in self.baris_ids],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': baru.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _baris_untuk(self, komponen, tingkat, jurusan):
        """Baris paling spesifik untuk komponen + tingkat + jurusan siswa.

        Urutan: tingkat+jurusan > tingkat > jurusan > umum. Kosong bila tidak ada baris yang cocok.
        """
        self.ensure_one()
        terbaik = self.env['nti_edu.tagihan.skema.baris']
        skor_terbaik = -1
        for baris in self.baris_ids.filtered(lambda b: b.komponen_id == komponen):
            if baris.tingkat_id and baris.tingkat_id != tingkat:
                continue
            if baris.jurusan_id and baris.jurusan_id != jurusan:
                continue
            skor = (2 if baris.tingkat_id else 0) + (1 if baris.jurusan_id else 0)
            if skor > skor_terbaik:
                terbaik, skor_terbaik = baris, skor
        return terbaik


class TagihanSkemaBaris(models.Model):
    _name = 'nti_edu.tagihan.skema.baris'
    _description = 'Baris Skema Biaya'
    _order = 'skema_id, komponen_id, tingkat_id, jurusan_id'
    _check_company_auto = True

    skema_id = fields.Many2one(
        'nti_edu.tagihan.skema', string='Skema', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', related='skema_id.company_id', store=True, index=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    komponen_id = fields.Many2one(
        'nti_edu.tagihan.komponen', string='Komponen', required=True, ondelete='restrict',
        domain="[('jenis', '=', 'biaya')]", check_company=True)
    tingkat_id = fields.Many2one(
        'nti_edu.tingkat', string='Tingkat', help='Kosong = semua tingkat.')
    jurusan_id = fields.Many2one(
        'nti_edu.jurusan', string='Jurusan', check_company=True, help='Kosong = semua jurusan.')
    nominal = fields.Monetary(string='Nominal', currency_field='currency_id', required=True)

    def init(self):
        # Kolom kosong dianggap sama: dua baris umum untuk komponen yang sama juga ditolak.
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS nti_edu_tagihan_skema_baris_unik
            ON nti_edu_tagihan_skema_baris
            (skema_id, komponen_id, COALESCE(tingkat_id, 0), COALESCE(jurusan_id, 0))
        """)

    @api.constrains('komponen_id', 'nominal')
    def _cek_baris(self):
        for rec in self:
            if rec.komponen_id.jenis != 'biaya':
                raise ValidationError(_(
                    'Komponen "%s" bukan komponen biaya sehingga tidak bisa masuk skema.', rec.komponen_id.name))
            if rec.nominal < 0:
                raise ValidationError(_('Nominal baris skema tidak boleh negatif.'))
