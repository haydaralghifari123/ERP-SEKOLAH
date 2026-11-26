# -*- coding: utf-8 -*-
import base64
import math
import re

from odoo import _, fields
from odoo.exceptions import UserError
from odoo.http import content_disposition, request, route

from odoo.addons.nti_edu_base.controllers.portal import NtiEduPortal

# Ruang untuk isian form dan pembungkus multipart di atas batas ukuran bukti unit.
CADANGAN_PERMINTAAN = 1024 * 1024

# Field form konfirmasi yang dikembalikan ke form saat galat (berkas tidak ikut).
ISIAN_KONFIRMASI = ('tanggal_transfer', 'nominal', 'rekening_id', 'nama_rekening_pengirim', 'catatan')


def _ke_int(nilai):
    """`int(nilai)` atau None bila bukan bilangan bulat."""
    try:
        return int(nilai)
    except (TypeError, ValueError):
        return None


class NtiEduTagihanPortal(NtiEduPortal):
    """Portal tagihan wali/siswa (spec §4.8).

    Anak yang boleh dilihat = helper base `_nti_edu_siswa_portal(termasuk_nonaktif=True)`, dengan anak nonaktif
    (lulus/pindah/keluar/diarsipkan) hanya bila masih punya tagihan terbuka. Semua data dibaca lewat `sudo` SETELAH
    siswa dipastikan ada di daftar itu dan tagihannya milik siswa itu; id dari permintaan tidak pernah dipercaya —
    selain itu 404.
    """

    # --- akses ---------------------------------------------------------------------------------

    def _nti_edu_tagihan_terbuka(self, siswa):
        """Tagihan sekolah terbit yang masih bersisa milik `siswa` (sudo), urut jatuh tempo terbuka."""
        Move = request.env['account.move'].sudo()
        if not siswa:
            return Move
        return Move.search([
            ('move_type', '=', 'out_invoice'), ('nti_edu_is_tagihan', '=', True), ('state', '=', 'posted'),
            ('nti_edu_siswa_id', 'in', siswa.ids), ('amount_residual', '>', 0),
        ], order='nti_edu_jatuh_tempo_terbuka, invoice_date, id').filtered(lambda m: m._nti_edu_terbuka())

    def _nti_edu_anak_tagihan(self):
        """Anak yang boleh dilihat tagihannya (sudo, urutan helper base): anak aktif, ditambah anak nonaktif yang
        masih punya tagihan terbuka."""
        anak = request.env.user._nti_edu_siswa_portal(termasuk_nonaktif=True)
        nonaktif = anak.filtered(lambda s: not s.active or s.nti_edu_status != 'aktif')
        bertunggakan = self._nti_edu_tagihan_terbuka(nonaktif).nti_edu_siswa_id
        return anak.filtered(lambda s: s not in nonaktif or s in bertunggakan)

    def _nti_edu_satu_anak(self, siswa_id):
        """Anak `siswa_id` bila boleh dilihat tagihannya; selain itu 404."""
        siswa_id = _ke_int(siswa_id)
        anak = self._nti_edu_anak_tagihan().filtered(lambda a: a.id == siswa_id)
        if not siswa_id or not anak:
            raise request.not_found()
        return anak

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'nti_edu_tagihan_count' in counters:
            values['nti_edu_tagihan_count'] = len(self._nti_edu_tagihan_terbuka(self._nti_edu_anak_tagihan()))
        return values

    # --- halaman tagihan -----------------------------------------------------------------------

    @route('/my/tagihan', type='http', auth='user', website=True)
    def nti_edu_tagihan(self, siswa=None, **kw):
        anak_list = self._nti_edu_anak_tagihan()
        if siswa is not None:
            anak = self._nti_edu_satu_anak(siswa)
            request.session['nti_edu_anak_id'] = anak.id
        else:
            anak = anak_list.filtered(lambda a: a.id == request.session.get('nti_edu_anak_id'))[:1] or anak_list[:1]
        values = self._prepare_portal_layout_values()
        values.update({
            'anak_list': anak_list,
            'anak': anak,
            'sendiri': request.env.user.sudo().partner_id.nti_edu_is_siswa,
            'page_name': 'nti_edu_tagihan',
        })
        if anak:
            values.update(self._nti_edu_nilai_tagihan(anak))
        return request.render('nti_edu_tagihan.portal_my_tagihan', values)

    def _nti_edu_nilai_tagihan(self, anak):
        """Isi halaman tagihan satu anak (sudo; `anak` sudah diperiksa)."""
        Move = request.env['account.move'].sudo()
        semua = Move.search([
            ('move_type', '=', 'out_invoice'), ('nti_edu_is_tagihan', '=', True), ('state', '=', 'posted'),
            ('nti_edu_siswa_id', '=', anak.id),
        ], order='invoice_date desc, id desc')
        # Nota kredit tampil sebagai pengurang tagihan yang dikoreksinya, bukan sebagai baris sendiri.
        nota = Move.search([
            ('move_type', '=', 'out_refund'), ('state', '=', 'posted'), ('reversed_entry_id', 'in', semua.ids)])
        rincian = {
            t.id: anak._nti_edu_rincian_kartu(t, nota.filtered(lambda n, t=t: n.reversed_entry_id == t))
            for t in semua
        }
        terbuka = semua.filtered(lambda m: m._nti_edu_terbuka()).sorted(
            lambda m: (m.nti_edu_jatuh_tempo_terbuka or m.invoice_date_due or fields.Date.today(), m.id))
        riwayat = semua.filtered('nti_edu_lunas')
        rekening = [
            (unit, request.env['nti_edu.tagihan.rekening'].sudo()._untuk_unit(unit))
            for unit in terbuka.company_id.sorted(lambda c: (c.name, c.id))
        ]
        TahunAjaran = request.env['nti_edu.tahun.ajaran'].sudo()
        tahun_list = (semua.nti_edu_tahun_ajaran_id | TahunAjaran._get_aktif()).sorted(
            lambda t: t.tanggal_mulai, reverse=True)
        return {
            'tagihan_terbuka': terbuka,
            'tagihan_riwayat': riwayat,
            'rincian': rincian,
            'mata_uang': anak.company_id.currency_id or request.env.company.currency_id,
            'sisa_tagihan': anak.nti_edu_sisa_tagihan,
            'tunggakan': anak.nti_edu_tunggakan,
            'saldo_kredit': anak.nti_edu_saldo_kredit,
            'rekening_per_unit': rekening,
            'tahun_list': tahun_list,
            'hari_ini': fields.Date.context_today(request.env.user),
            'konfirmasi_list': self._nti_edu_konfirmasi_saya(anak),
        }

    def _nti_edu_konfirmasi_saya(self, anak=None):
        """Konfirmasi transfer yang dikirim user ini (sudo), opsional hanya yang memuat `anak`."""
        domain = [('pengirim_id', '=', request.env.user.sudo().partner_id.id)]
        if anak:
            domain.append(('siswa_ids', 'in', anak.ids))
        return request.env['nti_edu.tagihan.konfirmasi'].sudo().search(domain, limit=50)

    # --- konfirmasi transfer -------------------------------------------------------------------

    @route('/my/tagihan/konfirmasi', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def nti_edu_tagihan_konfirmasi(self, unit=None, terkirim=None, **post):
        anak_list = self._nti_edu_anak_tagihan()
        terbuka = self._nti_edu_tagihan_terbuka(anak_list)
        unit_list = terbuka.company_id.sorted(lambda c: (c.name, c.id))
        konfirmasi_baru = request.env['nti_edu.tagihan.konfirmasi'].sudo()
        galat = False
        isian = {}
        dipilih = terbuka.browse()
        if request.httprequest.method == 'POST':
            isian = {f: (post.get(f) or '').strip() for f in ISIAN_KONFIRMASI}
            pilihan_ids = request.httprequest.form.getlist('tagihan_ids')
            dipilih = terbuka.filtered(lambda m: str(m.id) in pilihan_ids)
            try:
                # Savepoint: galat di tengah pembuatan tidak meninggalkan data setengah jadi.
                with request.env.cr.savepoint():
                    konfirmasi = self._nti_edu_kirim_konfirmasi(terbuka, pilihan_ids, isian)
            except UserError as e:
                galat = e.args[0]
            else:
                return request.redirect('/my/tagihan/konfirmasi?terkirim=%d' % konfirmasi.id)
            # Form diisi ulang untuk unit tagihan yang dipilih (bila hanya satu unit).
            unit = dipilih.company_id if len(dipilih.company_id) == 1 else unit_list[:1]
        else:
            if terkirim:
                konfirmasi_baru = self._nti_edu_konfirmasi_saya().filtered(lambda k: k.id == _ke_int(terkirim))
            if unit is not None:
                unit = unit_list.filtered(lambda c: c.id == _ke_int(unit))
                if not unit:
                    raise request.not_found()
            else:
                unit = (konfirmasi_baru.company_id & unit_list) or unit_list[:1]
            # Bawaan: semua tagihan terbuka unit itu terpilih, nominal = jumlah sisanya.
            dipilih = terbuka.filtered(lambda m: m.company_id == unit)

        tagihan_unit = terbuka.filtered(lambda m: m.company_id == unit)
        mata_uang = unit.currency_id or request.env.company.currency_id
        if not isian:
            isian = {
                'tanggal_transfer': fields.Date.to_string(fields.Date.context_today(request.env.user)),
                'nominal': ('%.2f' % sum((dipilih & tagihan_unit).mapped('amount_residual'))).rstrip('0').rstrip('.'),
            }
        values = self._prepare_portal_layout_values()
        values.update({
            'unit_list': unit_list,
            'unit': unit,
            'tagihan_unit': tagihan_unit,
            'rincian': {t.id: t.nti_edu_siswa_id._nti_edu_rincian_kartu(t, t.browse()) for t in tagihan_unit},
            'rekening_list': request.env['nti_edu.tagihan.rekening'].sudo()._untuk_unit(unit) if unit else [],
            'dipilih_ids': set(dipilih.ids),
            'isian': isian,
            'galat': galat,
            'mata_uang': mata_uang,
            'maks_mb': unit.nti_edu_bukti_ukuran_maks_mb if unit else 0,
            'konfirmasi_baru': konfirmasi_baru,
            'konfirmasi_list': self._nti_edu_konfirmasi_saya(),
            'page_name': 'nti_edu_tagihan_konfirmasi',
        })
        return request.render('nti_edu_tagihan.portal_my_tagihan_konfirmasi', values)

    def _nti_edu_kirim_konfirmasi(self, terbuka, pilihan_ids, isian):
        """Ubah isian form menjadi nilai `_buat_dari_portal` (yang memeriksa ulang semuanya di server).

        Berkas bukti ditolak sebelum di-base64 bila melebihi batas ukuran unit tagihan terpilih."""
        tagihan_ids = [_ke_int(i) for i in pilihan_ids]
        if None in tagihan_ids:
            raise UserError(_('Tagihan yang dipilih tidak ditemukan atau bukan tagihan anak Anda.'))
        try:
            nominal = float(isian['nominal'] or 0)
        except ValueError:
            raise UserError(_('Nominal transfer tidak valid.')) from None
        if not math.isfinite(nominal):
            raise UserError(_('Nominal transfer tidak valid.'))
        try:
            tanggal = fields.Date.to_date(isian['tanggal_transfer'] or None)
        except ValueError:
            raise UserError(_('Tanggal transfer tidak valid.')) from None

        # Batas ukuran dari unit tagihan terpilih (milik anak sendiri); bila pilihan tidak sah, berkas tidak dibaca
        # dan `_buat_dari_portal` menolak tagihannya lebih dahulu.
        unit = terbuka.filtered(lambda m: m.id in tagihan_ids).company_id
        bukti, bukti_nama = False, False
        if unit:
            maks_mb = max(unit.mapped('nti_edu_bukti_ukuran_maks_mb'))
            maks = maks_mb * 1024 * 1024
            berkas = request.httprequest.files.get('bukti')
            if not berkas or not berkas.filename:
                raise UserError(_('Bukti transfer wajib diunggah.'))
            if (request.httprequest.content_length or 0) > maks + CADANGAN_PERMINTAAN:
                raise UserError(_('Ukuran bukti transfer melebihi batas %s MB.', maks_mb))
            isi = berkas.stream.read(maks + 1)
            if len(isi) > maks:
                raise UserError(_('Ukuran bukti transfer melebihi batas %s MB.', maks_mb))
            bukti, bukti_nama = base64.b64encode(isi), berkas.filename

        return request.env['nti_edu.tagihan.konfirmasi']._buat_dari_portal(request.env.user, tagihan_ids, {
            'tanggal_transfer': tanggal,
            'nominal': nominal,
            'rekening_id': _ke_int(isian['rekening_id']) or False,
            'nama_rekening_pengirim': isian['nama_rekening_pengirim'],
            'bukti': bukti,
            'bukti_nama': bukti_nama,
            'catatan': isian['catatan'] or False,
        })

    # --- PDF -----------------------------------------------------------------------------------

    @route('/my/tagihan/kartu/<int:siswa_id>', type='http', auth='user', website=True)
    def nti_edu_tagihan_kartu(self, siswa_id, tahun=None, **kw):
        anak = self._nti_edu_satu_anak(siswa_id)
        TahunAjaran = request.env['nti_edu.tahun.ajaran'].sudo()
        if tahun is not None:
            ta = TahunAjaran.browse(_ke_int(tahun) or []).exists()
        else:
            ta = TahunAjaran._get_aktif()
        if not ta:
            raise request.not_found()
        pdf, _format = request.env['ir.actions.report'].sudo().with_company(anak.company_id)._render_qweb_pdf(
            'nti_edu_tagihan.action_report_kartu_spp', anak.ids, data={'tahun_ajaran_id': ta.id})
        nama = '%s.pdf' % re.sub(r'\W+', '_', 'Kartu SPP %s %s' % (anak.name, ta.name))
        return request.make_response(pdf, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf)),
            ('Content-Disposition', content_disposition(nama, disposition_type='inline')),
        ])

    @route('/my/tagihan/invoice/<int:move_id>', type='http', auth='user', website=True)
    def nti_edu_tagihan_invoice(self, move_id, **kw):
        tagihan = request.env['account.move'].sudo().browse(move_id).exists()
        if not tagihan or tagihan.move_type != 'out_invoice' or not tagihan.nti_edu_is_tagihan \
                or tagihan.state != 'posted' or tagihan.nti_edu_siswa_id not in self._nti_edu_anak_tagihan():
            raise request.not_found()
        return self._show_report(model=tagihan, report_type='pdf', report_ref='account.account_invoices')
