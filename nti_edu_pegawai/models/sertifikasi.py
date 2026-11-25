# -*- coding: utf-8 -*-
from odoo import fields, models


class PegawaiSertifikasi(models.Model):
    _name = 'nti_edu.pegawai.sertifikasi'
    _description = 'Sertifikasi Pegawai'
    _order = 'tahun desc, id desc'

    partner_id = fields.Many2one('res.partner', string='Pegawai', required=True, ondelete='cascade', index=True)
    jenis = fields.Selection([('pendidik', 'Sertifikat Pendidik'), ('lainnya', 'Lainnya')],
                             string='Jenis', required=True, default='pendidik')
    nomor = fields.Char(string='Nomor')
    tahun = fields.Integer(string='Tahun')
    bidang = fields.Char(string='Bidang')
    mapel_id = fields.Many2one('nti_edu.mapel', string='Mata Pelajaran')
    lampiran = fields.Binary(string='Lampiran', attachment=True)
