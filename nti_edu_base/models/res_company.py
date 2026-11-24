# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    nti_edu_jenis = fields.Selection(
        [('yayasan', 'Yayasan'), ('unit', 'Unit Sekolah')],
        string='Jenis Entitas', default='unit', required=True)
    nti_edu_jenjang_id = fields.Many2one('nti_edu.jenjang', string='Jenjang')
    nti_edu_npsn = fields.Char(string='NPSN')
    nti_edu_kode = fields.Char(string='Kode Unit')
    nti_edu_kepala_id = fields.Many2one('res.users', string='Kepala Sekolah')
    nti_edu_hari_sekolah = fields.Selection(
        [('5', '5 hari'), ('6', '6 hari')], string='Hari Sekolah', default='5')

    def _nti_edu_hari_efektif(self, tanggal):
        """True bila `tanggal` adalah hari efektif sekolah untuk unit ini (self = satu company).

        Bukan hari efektif: Minggu, Sabtu pada unit 5 hari, atau tanggal yang tercakup hari libur
        (global, milik unit ini, atau milik yayasan induknya)."""
        self.ensure_one()
        hari = tanggal.weekday()
        if hari == 6 or (hari == 5 and self.nti_edu_hari_sekolah == '5'):
            return False
        # sudo: libur tingkat yayasan harus terlihat oleh semua unit, apa pun record rule pemanggil.
        libur = self.env['nti_edu.hari.libur'].sudo().search_count([
            ('company_id', 'in', [False, self.id, self.parent_id.id]),
            ('tanggal_mulai', '<=', tanggal),
            '|', '&', ('tanggal_selesai', '=', False), ('tanggal_mulai', '=', tanggal),
            ('tanggal_selesai', '>=', tanggal),
        ])
        return not libur

    @api.constrains('nti_edu_kode')
    def _cek_kode_unik(self):
        for rec in self.filtered('nti_edu_kode'):
            lain = self.with_context(active_test=False).search_count([
                ('nti_edu_kode', '=', rec.nti_edu_kode), ('id', '!=', rec.id)])
            if lain:
                raise ValidationError(_('Kode unit "%s" sudah dipakai unit lain.', rec.nti_edu_kode))
