# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Rombel(models.Model):
    _name = 'nti_edu.rombel'
    _description = 'Rombongan Belajar'
    _order = 'tahun_ajaran_id desc, name'
    _check_company_auto = True

    name = fields.Char(string='Nama', required=True)
    tahun_ajaran_id = fields.Many2one(
        'nti_edu.tahun.ajaran', string='Tahun Ajaran', required=True, ondelete='restrict')
    tingkat_id = fields.Many2one('nti_edu.tingkat', string='Tingkat', required=True)
    jurusan_id = fields.Many2one('nti_edu.jurusan', string='Jurusan', check_company=True)
    company_id = fields.Many2one(
        'res.company', string='Unit Sekolah', required=True, default=lambda self: self.env.company)
    wali_kelas_id = fields.Many2one('res.users', string='Wali Kelas')
    ruang_id = fields.Many2one('nti_edu.ruang', string='Ruang', check_company=True)
    anggota_ids = fields.One2many('nti_edu.rombel.anggota', 'rombel_id', string='Anggota')
    jumlah_siswa = fields.Integer(string='Jumlah Siswa', compute='_compute_jumlah_siswa')

    _sql_constraints = [
        ('nama_unik', 'unique(name, tahun_ajaran_id, company_id)',
         'Nama rombel sudah dipakai pada tahun ajaran dan unit yang sama.'),
    ]

    @api.constrains('company_id')
    def _check_company_unit(self):
        for rec in self.sudo():
            if rec.company_id.nti_edu_jenis != 'unit':
                raise ValidationError(_('"%s" harus milik unit sekolah, bukan yayasan.', rec.display_name))

    @api.constrains('company_id')
    def _check_unit_anggota(self):
        for rec in self.sudo():
            if rec.anggota_ids.filtered(
                    lambda a: not a.tanggal_keluar and a.siswa_id.company_id != rec.company_id):
                raise ValidationError(_(
                    'Rombel "%s" masih berisi siswa dari unit lain.', rec.name))

    @api.depends('anggota_ids.tanggal_keluar')
    def _compute_jumlah_siswa(self):
        for rec in self:
            rec.jumlah_siswa = len(rec.anggota_ids.filtered(lambda a: not a.tanggal_keluar))


class RombelAnggota(models.Model):
    _name = 'nti_edu.rombel.anggota'
    _description = 'Keanggotaan Rombel'
    _order = 'rombel_id, no_absen, id'

    rombel_id = fields.Many2one('nti_edu.rombel', string='Rombel', required=True, ondelete='cascade')
    siswa_id = fields.Many2one(
        'res.partner', string='Siswa', required=True, domain=[('nti_edu_is_siswa', '=', True)])
    tahun_ajaran_id = fields.Many2one(
        related='rombel_id.tahun_ajaran_id', store=True, string='Tahun Ajaran')
    company_id = fields.Many2one(related='rombel_id.company_id', store=True, string='Unit Sekolah')
    no_absen = fields.Integer(string='No. Absen')
    tanggal_masuk = fields.Date(string='Tanggal Masuk')
    tanggal_keluar = fields.Date(string='Tanggal Keluar')

    @api.constrains('siswa_id', 'tahun_ajaran_id', 'tanggal_keluar')
    def _check_satu_rombel_per_tahun(self):
        Anggota = self.env['nti_edu.rombel.anggota'].sudo().with_context(active_test=False)
        for rec in self.sudo().filtered(lambda a: not a.tanggal_keluar):
            if Anggota.search_count([
                    ('id', '!=', rec.id), ('siswa_id', '=', rec.siswa_id.id),
                    ('tahun_ajaran_id', '=', rec.tahun_ajaran_id.id), ('tanggal_keluar', '=', False)]):
                raise ValidationError(_(
                    'Siswa "%(siswa)s" sudah menjadi anggota rombel lain pada tahun ajaran %(tahun)s.',
                    siswa=rec.siswa_id.name, tahun=rec.tahun_ajaran_id.name))

    @api.constrains('tanggal_masuk', 'tanggal_keluar')
    def _check_tanggal(self):
        for rec in self:
            if rec.tanggal_masuk and rec.tanggal_keluar and rec.tanggal_keluar < rec.tanggal_masuk:
                raise ValidationError(_('Tanggal keluar tidak boleh sebelum tanggal masuk.'))

    @api.constrains('siswa_id', 'rombel_id')
    def _check_unit_siswa(self):
        for rec in self.sudo():
            if rec.siswa_id.company_id != rec.company_id:
                raise ValidationError(_(
                    'Siswa "%(siswa)s" tidak terdaftar pada unit rombel "%(rombel)s".',
                    siswa=rec.siswa_id.name, rombel=rec.rombel_id.name))
