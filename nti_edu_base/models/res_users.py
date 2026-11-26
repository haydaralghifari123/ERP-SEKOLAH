# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import AccessError, UserError

from .res_partner import FIELD_SISWA

# Field user yang merambat ke partner (res.users _inherits res.partner); company_id user bukan milik partner.
FIELD_USER_PARTNER_SISWA = FIELD_SISWA - {'company_id'}


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _nti_edu_siswa_portal(self, termasuk_nonaktif=False):
        """Siswa aktif yang boleh dilihat user ini (hasil sudo).

        Partner user sendiri bila siswa, ditambah semua siswa dari baris wali dengan partner user ini.
        Dibaca lewat sudo (bukan record rule); berlaku untuk user portal maupun internal.
        `termasuk_nonaktif`: ikut sertakan siswa yang status-nya bukan `aktif` (lulus/pindah/keluar) atau
        diarsipkan, mis. untuk tagihan yang masih terbuka; tetap hanya siswa yang terhubung dengan user ini.
        """
        self.ensure_one()
        partner = self.sudo().partner_id
        Wali = self.env['nti_edu.siswa.wali'].sudo()
        siswa = Wali.search([('partner_id', '=', partner.id)]).siswa_id | partner.filtered('nti_edu_is_siswa')
        if not termasuk_nonaktif:
            siswa = siswa.filtered(lambda s: s.active and s.nti_edu_status == 'aktif')
        return siswa.sorted(lambda s: (s.name, s.id))

    def write(self, vals):
        # Jalur "preferensi saya" menulis lewat sudo dan akan melewati penjaga tulis siswa di res.partner.
        if (not self.env.su and self.env.uid in self.ids
                and FIELD_USER_PARTNER_SISWA & set(vals) and self.env.user.sudo().partner_id.nti_edu_is_siswa):
            raise AccessError(_("Data siswa hanya dapat diubah oleh Operator Data Sekolah."))
        return super().write(vals)

    def _deactivate_portal_user(self, **post):
        # Jalur "hapus akun saya" mengarsipkan partner lewat sudo (melewati penjaga tulis siswa).
        if self.sudo().partner_id.filtered('nti_edu_is_siswa'):
            raise UserError(_("Akun siswa hanya bisa dinonaktifkan oleh Operator Data Sekolah."))
        return super()._deactivate_portal_user(**post)
