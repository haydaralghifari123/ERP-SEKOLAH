# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

GRUP_OPERATOR = 'nti_edu_pegawai.group_pegawai_operator'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    nti_edu_nuptk = fields.Char(string='NUPTK', copy=False, groups=GRUP_OPERATOR)
    nti_edu_nip = fields.Char(string='NIP', copy=False, groups=GRUP_OPERATOR)
    nti_edu_status_kepegawaian = fields.Selection([
        ('pns', 'PNS'), ('pppk', 'PPPK'), ('gty', 'GTY/PTY'), ('gtt', 'GTT/PTT'),
        ('honorer', 'Honorer'), ('lainnya', 'Lainnya'),
    ], string='Status Kepegawaian', groups=GRUP_OPERATOR)
    nti_edu_pendidikan_terakhir = fields.Selection([
        ('sma', 'SMA/Sederajat'), ('d1', 'D1'), ('d2', 'D2'), ('d3', 'D3'), ('d4', 'D4'),
        ('s1', 'S1'), ('s2', 'S2'), ('s3', 'S3'),
    ], string='Pendidikan Terakhir', groups=GRUP_OPERATOR)
    nti_edu_bidang_studi = fields.Char(string='Bidang Studi', groups=GRUP_OPERATOR)
    nti_edu_sertifikasi_ids = fields.One2many(
        'nti_edu.pegawai.sertifikasi', 'partner_id', string='Sertifikasi', groups=GRUP_OPERATOR)
    nti_edu_is_pegawai = fields.Boolean(
        string='Pegawai', compute='_compute_nti_edu_is_pegawai', store=True, index=True)

    @api.depends('employee_ids.active')
    def _compute_nti_edu_is_pegawai(self):
        for rec in self:
            pegawai = rec.sudo().with_context(active_test=False).employee_ids
            rec.nti_edu_is_pegawai = any(pegawai.mapped('active'))

    def _nti_edu_cek_unik(self, field, label):
        Partner = self.env['res.partner'].sudo().with_context(active_test=False)
        for rec in self.sudo().filtered(field):
            if Partner.search_count([('id', '!=', rec.id), (field, '=', rec[field])]):
                # Sengaja tidak menyebut pemilik/unit nomor yang sama.
                raise ValidationError(_("%(label)s %(nilai)s sudah terdaftar.", label=label, nilai=rec[field]))

    @api.constrains('nti_edu_nuptk')
    def _check_nti_edu_nuptk_unik(self):
        self._nti_edu_cek_unik('nti_edu_nuptk', 'NUPTK')

    @api.constrains('nti_edu_nip')
    def _check_nti_edu_nip_unik(self):
        self._nti_edu_cek_unik('nti_edu_nip', 'NIP')
