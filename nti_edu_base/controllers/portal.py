# -*- coding: utf-8 -*-
from odoo.http import request, route

from odoo.addons.portal.controllers.portal import CustomerPortal


class NtiEduPortal(CustomerPortal):

    # --- Akses anak: semua data dibaca lewat sudo SETELAH id dipastikan ada di helper ---

    def _nti_edu_anak_boleh(self):
        return request.env.user._nti_edu_siswa_portal()

    def _nti_edu_anak_aktif(self):
        """Anak aktif untuk halaman portal (sudo): pilihan di session bila masih diizinkan, selain itu anak pertama."""
        anak = self._nti_edu_anak_boleh()
        terpilih = anak.filtered(lambda a: a.id == request.session.get('nti_edu_anak_id'))
        return terpilih[:1] or anak[:1]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'nti_edu_anak_count' in counters:
            values['nti_edu_anak_count'] = len(self._nti_edu_anak_boleh())
        return values

    @route('/my/anak', type='http', auth='user', website=True)
    def nti_edu_anak(self, **kw):
        values = self._prepare_portal_layout_values()
        values.update({
            'anak_list': self._nti_edu_anak_boleh(),
            'anak_aktif': self._nti_edu_anak_aktif(),
            'sendiri': request.env.user.sudo().partner_id.nti_edu_is_siswa,
            'page_name': 'nti_edu_anak',
        })
        return request.render('nti_edu_base.portal_my_anak', values)

    @route('/my/anak/<int:siswa_id>', type='http', auth='user', website=True)
    def nti_edu_anak_profil(self, siswa_id, **kw):
        anak = self._nti_edu_anak_boleh().filtered(lambda a: a.id == siswa_id)
        if not anak:
            raise request.not_found()
        values = self._prepare_portal_layout_values()
        values.update({
            'anak': anak,
            'tahun_aktif': request.env['nti_edu.tahun.ajaran'].sudo()._get_aktif(),
            'page_name': 'nti_edu_anak',
        })
        return request.render('nti_edu_base.portal_my_anak_profil', values)

    @route('/my/anak/<int:siswa_id>/pilih', type='http', auth='user', website=True)
    def nti_edu_anak_pilih(self, siswa_id, **kw):
        anak = self._nti_edu_anak_boleh().filtered(lambda a: a.id == siswa_id)
        if not anak:
            raise request.not_found()
        request.session['nti_edu_anak_id'] = anak.id
        return request.redirect('/my')

    # --- Siswa tidak boleh mengubah data partner sendiri lewat /my/account (menulis via sudo) ---

    @route(['/my/account'], type='http', auth='user', website=True)
    def account(self, redirect=None, **post):
        if post and request.httprequest.method == 'POST' and request.env.user.sudo().partner_id.nti_edu_is_siswa:
            # Data siswa hanya diubah Operator Data Sekolah: abaikan kiriman, tampilkan halaman apa adanya.
            post = {}
        return super().account(redirect=redirect, **post)
