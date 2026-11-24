# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class TahunAjaran(models.Model):
    _name = 'nti_edu.tahun.ajaran'
    _description = 'Tahun Ajaran'
    _order = 'tanggal_mulai desc'

    name = fields.Char(string='Tahun Ajaran', required=True, help='Contoh: 2026/2027')
    tanggal_mulai = fields.Date(string='Tanggal Mulai', required=True)
    tanggal_selesai = fields.Date(string='Tanggal Selesai', required=True)
    is_aktif = fields.Boolean(string='Aktif', help='Hanya satu tahun ajaran yang boleh aktif.')
    semester_ids = fields.One2many('nti_edu.semester', 'tahun_ajaran_id', string='Semester')

    @api.constrains('tanggal_mulai', 'tanggal_selesai')
    def _cek_tanggal(self):
        for rec in self:
            if rec.tanggal_selesai <= rec.tanggal_mulai:
                raise ValidationError(
                    _('Tanggal selesai tahun ajaran "%s" harus setelah tanggal mulai.', rec.name))
        # Rentang baru tidak boleh membuat semester yang sudah ada keluar dari tahun ajaran.
        self.semester_ids._cek_tanggal()

    @api.constrains('is_aktif')
    def _cek_satu_aktif(self):
        if self.search_count([('is_aktif', '=', True)]) > 1:
            raise ValidationError(_('Hanya boleh ada satu tahun ajaran yang aktif.'))

    @api.model
    def _get_aktif(self):
        """Tahun ajaran yang sedang aktif (recordset kosong bila belum ada)."""
        return self.search([('is_aktif', '=', True)], limit=1)


class Semester(models.Model):
    _name = 'nti_edu.semester'
    _description = 'Semester'
    _order = 'tanggal_mulai desc'

    tahun_ajaran_id = fields.Many2one(
        'nti_edu.tahun.ajaran', string='Tahun Ajaran', required=True, ondelete='restrict')
    jenis = fields.Selection([('ganjil', 'Ganjil'), ('genap', 'Genap')], string='Jenis', required=True)
    name = fields.Char(string='Nama', compute='_compute_name', store=True)
    tanggal_mulai = fields.Date(string='Tanggal Mulai', required=True)
    tanggal_selesai = fields.Date(string='Tanggal Selesai', required=True)
    is_aktif = fields.Boolean(string='Aktif', help='Hanya satu semester per tahun ajaran yang boleh aktif.')

    _sql_constraints = [
        ('tahun_jenis_unik', 'unique(tahun_ajaran_id, jenis)',
         'Semester dengan jenis yang sama sudah ada di tahun ajaran ini.'),
    ]

    @api.depends('tahun_ajaran_id.name', 'jenis')
    def _compute_name(self):
        for rec in self:
            jenis = dict(self._fields['jenis'].selection).get(rec.jenis, '')
            rec.name = '%s - %s' % (rec.tahun_ajaran_id.name or '', jenis)

    @api.constrains('tanggal_mulai', 'tanggal_selesai', 'tahun_ajaran_id')
    def _cek_tanggal(self):
        for rec in self:
            if rec.tanggal_selesai <= rec.tanggal_mulai:
                raise ValidationError(
                    _('Tanggal selesai semester "%s" harus setelah tanggal mulai.', rec.name))
            tahun = rec.tahun_ajaran_id
            if rec.tanggal_mulai < tahun.tanggal_mulai or rec.tanggal_selesai > tahun.tanggal_selesai:
                raise ValidationError(
                    _('Semester "%s" harus berada di dalam rentang tahun ajaran.', rec.name))

    @api.constrains('is_aktif', 'tahun_ajaran_id')
    def _cek_satu_aktif(self):
        for rec in self.filtered('is_aktif'):
            lain = self.search_count([
                ('tahun_ajaran_id', '=', rec.tahun_ajaran_id.id),
                ('is_aktif', '=', True), ('id', '!=', rec.id)])
            if lain:
                raise ValidationError(
                    _('Hanya boleh ada satu semester aktif di tahun ajaran "%s".', rec.tahun_ajaran_id.name))

    @api.model
    def _get_aktif(self):
        """Semester aktif pada tahun ajaran aktif (recordset kosong bila tidak ada)."""
        return self.search([
            ('is_aktif', '=', True), ('tahun_ajaran_id.is_aktif', '=', True)], limit=1)
