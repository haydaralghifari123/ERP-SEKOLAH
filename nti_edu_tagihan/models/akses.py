# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import AccessError


class TagihanAkses(models.AbstractModel):
    """Penjaga hak untuk metode modul yang menulis dokumen akuntansi lewat `sudo()` (spec §4.11).

    Grup tagihan tidak punya hak tulis langsung pada `account.move`/`account.payment`; metode modul memeriksa
    grup dan unit pemanggil dengan `_nti_edu_cek_hak` lalu menulis sebagai superuser.
    """
    _name = 'nti_edu.tagihan.akses'
    _description = 'Penjaga Hak Tagihan'

    @api.model
    def _nti_edu_cek_hak(self, grup_xmlid, companies):
        """`AccessError` bila user bukan anggota `grup_xmlid` atau salah satu `companies` di luar unit yang
        diizinkan untuknya. Superuser selalu lolos."""
        if self.env.su:
            return
        user = self.env.user
        if not user.has_group(grup_xmlid):
            raise AccessError(_('Anda tidak memiliki hak untuk melakukan tindakan ini.'))
        luar = companies.sudo() - user.company_ids.sudo()
        if luar:
            raise AccessError(_(
                'Anda tidak memiliki akses ke unit %s.', ', '.join(luar.mapped('name'))))
