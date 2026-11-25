# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .res_partner import GRUP_HRD


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

    def _nti_edu_cek_tulis(self, partners):
        """Tulis sertifikasi = ubah profil orangnya; ikuti penjaga profil pada kontak."""
        if self.env.su:
            return
        Partner = self.env['res.partner']
        for partner in partners:
            if not Partner.browse(partner.id)._nti_edu_boleh_ubah_profil_pegawai():
                Partner._nti_edu_tolak_profil()

    @api.model_create_multi
    def create(self, vals_list):
        partners = self.env['res.partner'].browse([v['partner_id'] for v in vals_list if v.get('partner_id')])
        self._nti_edu_cek_tulis(partners)
        return super().create(vals_list)

    def write(self, vals):
        partners = self.sudo().partner_id
        if vals.get('partner_id'):
            partners |= self.env['res.partner'].browse(vals['partner_id'])
        self._nti_edu_cek_tulis(partners)
        return super().write(vals)

    def unlink(self):
        if not self.env.su and not self.env.user.has_group(GRUP_HRD):
            raise AccessError(_("Sertifikasi hanya boleh dihapus oleh HRD."))
        return super().unlink()
