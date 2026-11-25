# -*- coding: utf-8 -*-
import contextvars

from odoo import _, api, models
from odoo.exceptions import AccessError

from .res_partner import GRUP_HRD

# Field resource yang dicerminkan hr.employee (company_id, active, user_id, name, jam kerja, zona waktu).
FIELD_RESOURCE_PEGAWAI = ('company_id', 'active', 'user_id', 'name', 'calendar_id', 'tz')

# Resource yang sedang ditulis oleh hr.employee.write sesudah penjaga pegawai lolos (inverse field terkait berjalan
# dengan hak pemanggil, bukan sudo): frozenset id resource; True selama hr.employee.create sesudah penjaganya lolos
# (resource baru belum punya id; resource lama yang dipakai sudah dicek _nti_edu_cek_resource_baru).
# Sengaja ContextVar Python, bukan kunci konteks Odoo: pemanggil RPC bisa mengisi konteks sendiri, tetapi tidak
# bisa mengisi variabel ini.
RESOURCE_LEWAT_PEGAWAI = contextvars.ContextVar('nti_edu_resource_lewat_pegawai', default=frozenset())


class ResourceResource(models.Model):
    _inherit = 'resource.resource'

    def _nti_edu_perlu_hrd(self):
        return not self.env.su and not self.env.user.has_group(GRUP_HRD)

    @api.model_create_multi
    def create(self, vals_list):
        # Resource berakun = pegawai berakun begitu ditautkan ke hr.employee: hanya HRD (seperti user_id pegawai).
        if self._nti_edu_perlu_hrd() and any(vals.get('user_id') for vals in vals_list):
            raise AccessError(_("Akun login pegawai hanya boleh ditautkan oleh HRD."))
        return super().create(vals_list)

    def _nti_edu_berubah(self, vals):
        """Resource di `self` yang nilainya benar-benar berubah untuk field pegawai di `vals` (inverse field terkait
        saat hr.employee dibuat menulis ulang nilai yang sama), per field."""
        def nilai(rec, field):
            lama = rec[field]
            return (lama.id if isinstance(lama, models.BaseModel) else lama) or False

        hasil = {}
        for field in set(FIELD_RESOURCE_PEGAWAI) & set(vals):
            baru = vals[field] or False
            hasil[field] = self.sudo().filtered(lambda r: nilai(r, field) != baru).with_env(self.env)
        return hasil

    def write(self, vals):
        lewat_pegawai = RESOURCE_LEWAT_PEGAWAI.get()
        if (self and lewat_pegawai is not True and self._nti_edu_perlu_hrd()
                and set(FIELD_RESOURCE_PEGAWAI) & set(vals)):
            berubah = {f: recs.filtered(lambda r: r.id not in lewat_pegawai)
                       for f, recs in self._nti_edu_berubah(vals).items()}
            if berubah.get('user_id'):
                raise AccessError(_("Akun login pegawai hanya boleh ditautkan oleh HRD."))
            semua = self.browse().union(*berubah.values())
            if semua and self.env['hr.employee'].sudo().with_context(active_test=False).search_count(
                    [('resource_id', 'in', semua.ids)]):
                raise AccessError(_("Ubah data pegawai lewat menu Pegawai."))
        return super().write(vals)
