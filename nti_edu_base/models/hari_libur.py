# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HariLibur(models.Model):
    _name = 'nti_edu.hari.libur'
    _description = 'Hari Libur'
    _order = 'tanggal_mulai desc'

    name = fields.Char(string='Keterangan', required=True)
    tanggal_mulai = fields.Date(string='Tanggal Mulai', required=True)
    tanggal_selesai = fields.Date(string='Tanggal Selesai', help='Kosong = libur satu hari.')
    company_id = fields.Many2one(
        'res.company', string='Unit / Yayasan', ondelete='cascade', help='Kosong = berlaku untuk semua unit.')
    jenis = fields.Selection(
        [('nasional', 'Libur Nasional'), ('sekolah', 'Libur Sekolah'),
         ('ujian', 'Masa Ujian'), ('lainnya', 'Lainnya')],
        string='Jenis', required=True, default='lainnya')

    @api.constrains('tanggal_mulai', 'tanggal_selesai')
    def _cek_tanggal(self):
        for rec in self:
            if rec.tanggal_selesai and rec.tanggal_selesai < rec.tanggal_mulai:
                raise ValidationError(
                    _('Tanggal selesai libur "%s" tidak boleh sebelum tanggal mulai.', rec.name))
