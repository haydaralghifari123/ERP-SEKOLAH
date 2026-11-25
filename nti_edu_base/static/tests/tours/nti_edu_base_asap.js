/** Uji asap layar Data Sekolah: membuka setiap menu, view, dan form agar galat sisi klien (Owl) ketahuan. */
import { registry } from "@web/core/registry";

const APP = "nti_edu_base.menu_data_sekolah";

function langkahMenu({ xmlid, induk, views = [], form = false }) {
    const langkah = [];
    if (induk) {
        langkah.push(
            {
                content: `Buka menu induk ${induk}`,
                trigger: `.o_menu_sections button[data-menu-xmlid="nti_edu_base.${induk}"]`,
                run: "click",
            },
            {
                content: `Pilih menu ${xmlid}`,
                trigger: `.dropdown-menu [data-menu-xmlid="nti_edu_base.${xmlid}"]`,
                run: "click",
            }
        );
    } else {
        langkah.push({
            content: `Pilih menu ${xmlid}`,
            trigger: `.o_menu_sections [data-menu-xmlid="nti_edu_base.${xmlid}"]`,
            run: "click",
        });
    }
    for (const view of views) {
        if (view === "kanban") {
            langkah.push(
                { content: "Ganti ke kanban", trigger: ".o_switch_view.o_kanban", run: "click" },
                {
                    content: "Kanban tampil dengan kartu",
                    trigger: ".o_kanban_view .o_kanban_record:not(.o_kanban_ghost)",
                }
            );
        } else {
            langkah.push(
                { content: "Ganti ke list", trigger: ".o_switch_view.o_list", run: "click" },
                { content: "List tampil dengan baris", trigger: ".o_list_view .o_data_row" }
            );
        }
    }
    if (!views.length) {
        langkah.push({ content: "List tampil", trigger: ".o_list_view" });
    }
    if (form) {
        langkah.push(
            { content: "Buka record pertama", trigger: ".o_list_view .o_data_row:first td.o_data_cell, .o_kanban_view .o_kanban_record:not(.o_kanban_ghost):first", run: "click" },
            { content: "Form tampil", trigger: ".o_form_view .o_form_sheet" },
            { content: "Kembali", trigger: ".o_back_button", run: "click" },
            { content: "Daftar tampil lagi", trigger: ".o_list_view .o_data_row, .o_kanban_view .o_kanban_record" }
        );
    }
    return langkah;
}

function langkahWizard() {
    return [
        { content: "Ke list siswa", trigger: ".o_menu_sections [data-menu-xmlid='nti_edu_base.menu_siswa']", run: "click" },
        { content: "Ganti ke list", trigger: ".o_switch_view.o_list", run: "click" },
        {
            content: "Centang satu siswa",
            trigger: ".o_list_view .o_data_row:first .o_list_record_selector input",
            run: "click",
        },
        {
            content: "Klik Tambah ke Rombel",
            trigger: ".o_control_panel button:contains('Tambah ke Rombel')",
            run: "click",
        },
        { content: "Wizard tampil", trigger: ".modal .o_form_view" },
        { content: "Batal", trigger: ".modal-footer button:contains('Batal')", run: "click" },
        { content: "Ke menu Rombel", trigger: ".o_menu_sections [data-menu-xmlid='nti_edu_base.menu_rombel']", run: "click" },
        { content: "Buka rombel pertama", trigger: ".o_list_view .o_data_row:first td.o_data_cell", run: "click" },
        { content: "Klik Kenaikan Kelas", trigger: ".o_form_view button:contains('Kenaikan Kelas')", run: "click" },
        { content: "Wizard kenaikan tampil", trigger: ".modal .o_form_view" },
        { content: "Tutup", trigger: ".modal-footer button:contains('Tutup')", run: "click" },
        { content: "Form rombel kembali", trigger: ".o_form_view .o_form_sheet" },
    ];
}

const menuUmum = () => [
    ...langkahMenu({ xmlid: "menu_siswa", views: ["list", "kanban"], form: true }),
    ...langkahMenu({ xmlid: "menu_rombel", form: true }),
    ...langkahMenu({ xmlid: "menu_tahun_ajaran", induk: "menu_kalender", form: true }),
    ...langkahMenu({ xmlid: "menu_hari_libur", induk: "menu_kalender" }),
];

const mulai = () => [
    {
        content: "Buka menu aplikasi",
        trigger: ".o_navbar_apps_menu button:enabled",
        run: "click",
    },
    {
        content: "Buka aplikasi Data Sekolah",
        trigger: `.o_app[data-menu-xmlid="${APP}"]`,
        run: "click",
    },
];

registry.category("web_tour.tours").add("nti_edu_base_asap", {
    steps: () => [
        ...mulai(),
        ...menuUmum(),
        ...langkahMenu({ xmlid: "menu_wali", form: true }),
        ...langkahMenu({ xmlid: "menu_unit", induk: "menu_konfigurasi", form: true }),
        ...langkahMenu({ xmlid: "menu_jenjang", induk: "menu_konfigurasi", form: true }),
        ...langkahMenu({ xmlid: "menu_jurusan", induk: "menu_konfigurasi" }),
        ...langkahMenu({ xmlid: "menu_mapel", induk: "menu_konfigurasi" }),
        ...langkahMenu({ xmlid: "menu_ruang", induk: "menu_konfigurasi" }),
        ...langkahWizard(),
    ],
});

registry.category("web_tour.tours").add("nti_edu_base_asap_operator", {
    steps: () => [
        ...mulai(),
        ...menuUmum(),
        ...langkahMenu({ xmlid: "menu_wali", form: true }),
        ...langkahWizard(),
    ],
});
