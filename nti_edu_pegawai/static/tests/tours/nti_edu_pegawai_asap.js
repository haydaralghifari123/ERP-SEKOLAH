/** Uji asap layar Pegawai: kanban, list, form (tab Kepegawaian + simpan sertifikasi), dan dua wizard (dibuka lalu dibatalkan). */
import { registry } from "@web/core/registry";

const REMAH = ".o_control_panel .o_last_breadcrumb_item.active";
const KARTU = ".o_kanban_view .o_kanban_record:not(.o_kanban_ghost)";
const BARIS = ".o_list_view .o_data_row";

// Tunggu layar baru lewat judul remah roti (unik per layar), baru periksa isinya.
const judul = (nama) => ({ content: `Layar ${nama} tampil`, trigger: `${REMAH}:contains('${nama}')` });
const tanpaModal = (content) => ({ content, trigger: "body:not(:has(.modal))" });

// Buka form pegawai dari list lewat nama, tunggu form untuk orang itu tampil.
const bukaPegawai = (nama) => [
    { content: `Buka ${nama}`, trigger: `${BARIS}:contains('${nama}') td.o_data_cell:first`, run: "click" },
    { content: `Form ${nama} tampil`, trigger: `.o_form_view .o_form_sheet .o_field_widget[name=name] input:value('${nama}')` },
];

const kembaliKeList = () => [
    { content: "Kembali", trigger: ".o_back_button", run: "click" },
    judul("Pegawai"),
    { content: "List tampil lagi", trigger: BARIS },
];

registry.category("web_tour.tours").add("nti_edu_pegawai_asap", {
    steps: () => [
        { content: "Buka menu aplikasi", trigger: ".o_navbar_apps_menu button:enabled", run: "click" },
        {
            content: "Buka aplikasi Data Sekolah",
            trigger: '.o_app[data-menu-xmlid="nti_edu_base.menu_data_sekolah"]',
            run: "click",
        },
        {
            content: "Pilih menu Pegawai",
            trigger: '.o_menu_sections [data-menu-xmlid="nti_edu_pegawai.menu_pegawai"]',
            run: "click",
        },
        judul("Pegawai"),
        { content: "Kanban tampil dengan kartu", trigger: KARTU },
        { content: "Ganti ke list", trigger: ".o_switch_view.o_list", run: "click" },
        { content: "List tampil dengan baris", trigger: BARIS },
        ...bukaPegawai("Pegawai Dua Unit UI"),
        { content: "Buka tab Kepegawaian", trigger: ".o_notebook .nav-link:contains('Kepegawaian')", run: "click" },
        { content: "Tab Kepegawaian tampil", trigger: ".o_notebook .tab-pane.active [name=nti_edu_sertifikasi_ids]" },
        // Simpan sertifikasi lewat klien web nyata (id virtual, web_save).
        {
            content: "Tambah baris sertifikasi",
            trigger: "[name=nti_edu_sertifikasi_ids] .o_field_x2many_list_row_add a",
            run: "click",
        },
        {
            content: "Isi nomor sertifikasi",
            trigger: "[name=nti_edu_sertifikasi_ids] .o_selected_row [name=nomor] input",
            run: "edit SERT-TOUR-1",
        },
        { content: "Simpan form", trigger: ".o_form_button_save", run: "click" },
        {
            content: "Tersimpan: tidak ada perubahan tertunda",
            trigger: ".o_form_status_indicator_buttons.invisible:not(:visible)",
        },
        {
            content: "Baris sertifikasi bertahan setelah simpan",
            trigger: "[name=nti_edu_sertifikasi_ids] .o_data_row:not(.o_selected_row):contains('SERT-TOUR-1')",
        },
        // Wizard Buat Akun Login: buka lalu tutup tanpa membuat akun.
        {
            content: "Klik Buat Akun Login",
            trigger: ".o_form_statusbar button:contains('Buat Akun Login')",
            run: "click",
        },
        { content: "Wizard akun tampil", trigger: ".modal .o_form_view" },
        { content: "Tutup wizard akun", trigger: ".modal-footer button:contains('Tutup')", run: "click" },
        tanpaModal("Wizard akun tertutup"),
        { content: "Form pegawai kembali", trigger: ".o_form_view .o_form_sheet" },
        ...kembaliKeList(),
        // Wizard Tempatkan di Unit Lain: orang yang hanya di satu unit.
        ...bukaPegawai("Pegawai Satu Unit UI"),
        {
            content: "Klik Tempatkan di Unit Lain",
            trigger: ".o_form_statusbar button:contains('Tempatkan di Unit Lain')",
            run: "click",
        },
        { content: "Wizard penempatan tampil", trigger: ".modal .o_form_view" },
        { content: "Batal", trigger: ".modal-footer button:contains('Batal')", run: "click" },
        tanpaModal("Wizard penempatan tertutup"),
        { content: "Form pegawai kembali", trigger: ".o_form_view .o_form_sheet" },
        ...kembaliKeList(),
    ],
});
