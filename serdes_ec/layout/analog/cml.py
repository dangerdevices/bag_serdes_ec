# -*- coding: utf-8 -*-

"""This package defines various passives template classes.
"""

from typing import Dict, Set, Any

from bag.util.search import BinaryIterator
from bag.layout.routing.base import TrackID, TrackManager
from bag.layout.template import TemplateBase, TemplateDB

from abs_templates_ec.analog_core.base import AnalogBaseInfo, AnalogBase


class CMLCorePMOS(AnalogBase):
    """PMOS gm cell for a CML driver.

    Parameters
    ----------
    temp_db : :class:`bag.layout.template.TemplateDB`
        the template database.
    lib_name : str
        the layout library name.
    params : Dict[str, Any]
        the parameter values.
    used_names : Set[str]
        a set of already used cell names.
    **kwargs :
        dictionary of optional parameters.  See documentation of
        :class:`bag.layout.template.TemplateBase` for details.
    """

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **kwargs) -> None
        AnalogBase.__init__(self, temp_db, lib_name, params, used_names, **kwargs)
        self._sch_params = None
        self._num_fingers = None

    @property
    def sch_params(self):
        # type: () -> Dict[str, Any]
        return self._sch_params

    @property
    def num_fingers(self):
        # type: () -> int
        return self._num_fingers

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        return dict(
            lch='channel length, in meters.',
            ntap_w='PMOS substrate width, in meters/number of fins.',
            w='pmos width, in meters/number of fins.',
            fg_ref='number of current mirror reference fingers per segment.',
            threshold='transistor threshold flavor.',
            output_tracks='output track indices on vm layer.',
            em_specs='EM specs per segment.',
            tr_widths='Track width dictionary.',
            tr_spaces='Track spacing dictionary.',
            tot_width='Total width in resolution units.',
            guard_ring_nf='Guard ring width in number of fingers.  0 for no guard ring.',
            show_pins='True to draw pins.',
        )

    @classmethod
    def get_default_param_values(cls):
        return dict(
            guard_ring_nf=0,
            show_pins=True,
        )

    def draw_layout(self):
        lch = self.params['lch']
        ntap_w = self.params['ntap_w']
        w = self.params['w']
        fg_ref = self.params['fg_ref']
        threshold = self.params['threshold']
        output_tracks = self.params['output_tracks']
        em_specs = self.params['em_specs']
        tr_widths = self.params['tr_widths']
        tr_spaces = self.params['tr_spaces']
        tot_width = self.params['tot_width']
        guard_ring_nf = self.params['guard_ring_nf']
        show_pins = self.params['show_pins']

        # get AnalogBaseInfo
        hm_layer = self.mos_conn_layer + 1
        ym_layer = hm_layer + 1
        layout_info = AnalogBaseInfo(self.grid, lch, guard_ring_nf, top_layer=ym_layer)

        # compute total number of fingers to achieve target width.
        bin_iter = BinaryIterator(2, None, step=2)
        while bin_iter.has_next():
            fg_cur = bin_iter.get_next()
            w_cur = layout_info.get_placement_info(fg_cur).tot_width
            if w_cur < tot_width:
                bin_iter.save()
                bin_iter.up()
            elif w_cur > tot_width:
                bin_iter.down()
            else:
                bin_iter.save()
                break

        fg_tot = bin_iter.get_last_save()
        # find number of tracks needed for output tracks from EM specs
        hm_tr_w_out = self.grid.get_min_track_width(hm_layer, **em_specs)
        hm_tr_sp_out = self.grid.get_num_space_tracks(hm_layer, hm_tr_w_out, half_space=True)
        hm_w = self.grid.get_track_width(hm_layer, hm_tr_w_out, unit_mode=True)
        ym_tr_w = self.grid.get_min_track_width(ym_layer, bot_w=hm_w, **em_specs, unit_mode=True)

        # construct track width/space dictionary from EM specs
        tr_manager = TrackManager(self.grid, tr_widths, tr_spaces, half_space=True)
        tr_w_dict = {
            'in': {hm_layer: tr_manager.get_width(hm_layer, 'in')},
            'out': {hm_layer: hm_tr_w_out, ym_tr_w: ym_tr_w},
        }
        tr_sp_dict = {
            ('in', 'out'): {hm_layer: max(hm_tr_sp_out,
                                          tr_manager.get_space(hm_layer, ('in', 'out')))},
        }
        tr_manager = TrackManager(self.grid, tr_w_dict, tr_sp_dict, half_space=True)

        pw_list = [w, w, w]
        pth_list = [threshold, threshold, threshold]
        wire_names = dict(
            nch=[],
            pch=[
                dict(ds=['out'],
                     g=['in'],
                     ),
                dict(g=['out'],
                     ds=['out'],
                     ds2=['out'],
                     ),
                dict(g=['in'],
                     ds=['out']),
            ],
        )
        # draw transistor rows
        self._num_fingers = fg_tot
        self.draw_base(lch, fg_tot, ntap_w, ntap_w, [], [], pw_list, pth_list,
                       tr_manager=tr_manager, wire_names=wire_names,
                       p_orientations=['MX', 'R0', 'R0'], guard_ring_nf=guard_ring_nf,
                       pgr_w=ntap_w, ngr_w=ntap_w, top_layer=ym_layer)

        outn_tid = self.get_wire_id('pch', 0, 'ds', wire_name='out')
        inp_tid = self.get_wire_id('pch', 0, 'g', wire_name='in')
        bias_tid = self.get_wire_id('pch', 1, 'g', wire_name='out')
        vdd_tid = self.get_wire_id('pch', 1, 'ds', wire_name='out')
        tail_tid = self.get_wire_id('pch', 1, 'ds2', wire_name='out')
        inn_tid = self.get_wire_id('pch', 2, 'g', wire_name='in')
        outp_tid = self.get_wire_id('pch', 2, 'ds', wire_name='out')

        out_delta = int(round(2 * (output_tracks[1] - output_tracks[0])))
        out_pitch = self.grid.get_track_pitch(ym_layer, unit_mode=True) // 2 * out_delta
        sd_pitch = layout_info.sd_pitch_unit
        if out_pitch % sd_pitch != 0:
            raise ValueError('Oops')
        fg = out_pitch // sd_pitch - fg_ref

        # draw transistors and connect
        inp_list = []
        inn_list = []
        tail_list = []
        bias_list = []
        vdd_m_list = []
        outp_list = []
        outn_list = []
        col_first = col_last = None
        layout_info = self.layout_info
        for idx, ym_idx in enumerate(output_tracks):
            # TODO: add check that fg + fg_ref is less than or equal to output pitch?
            vtid = TrackID(ym_layer, ym_idx, width=ym_tr_w)
            # find column index that centers on given track index
            x_coord = self.grid.track_to_coord(ym_layer, ym_idx, unit_mode=True)
            col_center = layout_info.coord_to_col(x_coord, unit_mode=True)
            col_idx = col_center - (fg // 2)
            # draw transistors
            if idx == 0:
                col_first = col_idx - fg_ref
                mref = self.draw_mos_conn('pch', 1, col_idx - fg_ref, fg_ref, 2, 0,
                                          diode_conn=True, gate_pref_loc='d')
                bias_list.append(mref['g'])
                bias_list.append(mref['d'])
                vdd_m_list.append(mref['s'])

            mtop = self.draw_mos_conn('pch', 2, col_idx, fg, 2, 0, s_net='outp', d_net='tail')
            mbot = self.draw_mos_conn('pch', 0, col_idx, fg, 0, 2, s_net='outn', d_net='tail')
            mtail = self.draw_mos_conn('pch', 1, col_idx, fg, 2, 0, gate_pref_loc='s',
                                       s_net='', d_net='tail')
            mref = self.draw_mos_conn('pch', 1, col_idx + fg, fg_ref, 2, 0, gate_pref_loc='d',
                                      diode_conn=True, s_net='', d_net='tail')
            col_last = col_idx + fg + fg_ref
            # connect
            inp_list.append(mbot['g'])
            inn_list.append(mtop['g'])
            bias_list.append(mref['g'])
            bias_list.append(mref['d'])
            bias_list.append(mtail['g'])
            tail_list.append(mtop['d'])
            tail_list.append(mbot['d'])
            tail_list.append(mtail['d'])
            vdd_m_list.append(mtail['s'])
            vdd_m_list.append(mref['s'])

            outp_h = self.connect_to_tracks(mtop['s'], outp_tid)
            outp_list.append(outp_h)
            self.add_pin('outp', self.connect_to_tracks(outp_h, vtid), show=show_pins)
            outn_h = self.connect_to_tracks(mbot['s'], outn_tid)
            outn_list.append(outn_h)
            self.add_pin('outn', self.connect_to_tracks(outn_h, vtid), show=show_pins)

        self.connect_wires(outp_list)
        self.connect_wires(outn_list)
        self.add_pin('inp', self.connect_to_tracks(inp_list, inp_tid), show=show_pins)
        self.add_pin('inn', self.connect_to_tracks(inn_list, inn_tid), show=show_pins)
        self.connect_to_tracks(tail_list, tail_tid)
        self.add_pin('ibias', self.connect_to_tracks(bias_list, bias_tid), show=show_pins)
        self.add_pin('VDD_mid', self.connect_to_tracks(vdd_m_list, vdd_tid),
                     label='VDD', show=show_pins)

        ptap_warrs, ntap_warrs = self.fill_dummy()
        self.add_pin('VSS', ptap_warrs, show=show_pins)
        self.add_pin('VDD', ntap_warrs, show=show_pins)


class CMLDriverPMOS(TemplateBase):
    """An template for creating high pass filter.

    Parameters
    ----------
    temp_db : :class:`bag.layout.template.TemplateDB`
            the template database.
    lib_name : str
        the layout library name.
    params : dict[str, any]
        the parameter values.
    used_names : set[str]
        a set of already used cell names.
    **kwargs :
        dictionary of optional parameters.  See documentation of
        :class:`bag.layout.template.TemplateBase` for details.
    """

    def __init__(self, temp_db, lib_name, params, used_names, **kwargs):
        # type: (TemplateDB, str, Dict[str, Any], Set[str], **Any) -> None
        super(CMLDriverPMOS, self).__init__(temp_db, lib_name, params, used_names, **kwargs)
        self._num_fingers = None

    @property
    def num_fingers(self):
        return self._num_fingers

    @classmethod
    def get_default_param_values(cls):
        # type: () -> Dict[str, Any]
        """Returns a dictionary containing default parameter values.

        Override this method to define default parameter values.  As good practice,
        you should avoid defining default values for technology-dependent parameters
        (such as channel length, transistor width, etc.), but only define default
        values for technology-independent parameters (such as number of tracks).

        Returns
        -------
        default_params : Dict[str, Any]
            dictionary of default parameter values.
        """
        return dict(
            show_pins=True,
        )

    @classmethod
    def get_params_info(cls):
        # type: () -> Dict[str, str]
        """Returns a dictionary containing parameter descriptions.

        Override this method to return a dictionary from parameter names to descriptions.

        Returns
        -------
        param_info : Dict[str, str]
            dictionary from parameter name to description.
        """
        return dict(
            res_params='load resistor parameters.',
            lch='channel length, in meters.',
            w='pmos width, in meters/number of fins.',
            fg='number of fingers per segment.',
            fg_ref='number of current mirror reference fingers per segment.',
            threshold='transistor threshold flavor.',
            input_width='input track width',
            input_space='input track space',
            ntap_w='PMOS substrate width, in meters/number of fins.',
            guard_ring_nf='Guard ring width in number of fingers.  0 for no guard ring.',
            top_layer='top level layer',
            show_pins='True to draw pins.',
        )

    def draw_layout(self):
        # type: () -> None
        self._draw_layout_helper(**self.params)

    def _draw_layout_helper(self, res_params, lch, w, fg, fg_ref, threshold, input_width,
                            input_space, ntap_w, guard_ring_nf, show_pins, top_layer):

        sub_params = dict(
            lch=lch,
            w=ntap_w,
        )

        load_params = dict(
            res_params=res_params.copy(),
            sub_params=sub_params,
            show_pins=False,
        )

        load_master = self.new_template(params=load_params, temp_cls=CMLLoadSingle)

        core_params = dict(
            lch=lch,
            w=w,
            fg=fg,
            fg_ref=fg_ref,
            output_tracks=load_master.output_tracks,
            em_specs=res_params['em_specs'].copy(),
            threshold=threshold,
            input_width=input_width,
            input_space=input_space,
            ntap_w=ntap_w,
            guard_ring_nf=guard_ring_nf,
            tot_width=load_master.array_box.width,
            show_pins=False,
        )

        core_master = self.new_template(params=core_params, temp_cls=CMLCorePMOS)
        self._num_fingers = core_master.num_fingers

        # place instances
        _, load_height = self.grid.get_size_dimension(load_master.size, unit_mode=True)
        _, core_height = self.grid.get_size_dimension(core_master.size, unit_mode=True)
        loadn = self.add_instance(load_master, 'XLOADN', (0, load_height), orient='MX',
                                  unit_mode=True)
        core = self.add_instance(core_master, 'XCORE', (0, load_height), unit_mode=True)
        loadp = self.add_instance(load_master, 'XLOADP', (0, load_height + core_height),
                                  unit_mode=True)

        self.array_box = loadn.array_box.merge(loadp.array_box)
        self.size = self.grid.get_size_tuple(top_layer, self.array_box.width_unit,
                                             self.array_box.height_unit,
                                             round_up=True, unit_mode=True)

        for name in ['inp', 'inn', 'ibias', 'VDD']:
            label = name + ':' if name == 'VDD' else name
            self.reexport(core.get_port(name), label=label, show=show_pins)

        # connect outputs
        outp_list = self.connect_wires(
            loadp.get_all_port_pins('out') + core.get_all_port_pins('outp'))
        outn_list = self.connect_wires(
            loadn.get_all_port_pins('out') + core.get_all_port_pins('outn'))
        outp_list = outp_list[0].to_warr_list()
        outn_list = outn_list[0].to_warr_list()
        vddm = core.get_all_port_pins('VDDM')
        vsst = loadp.get_all_port_pins('VSS')
        vssb = loadn.get_all_port_pins('VSS')

        em_specs = res_params['em_specs']

        for warrs, name in [(outp_list, 'outp'), (outn_list, 'outn'),
                            (vddm, 'VDD'), (vsst, 'VSS'), (vssb, 'VSS')]:
            self._connect_to_top(name, warrs, em_specs, top_layer, show_pins)

    def _connect_to_top(self, name, warrs, em_specs, top_layer, show_pins):
        num_seg = len(warrs)
        prev_layer = warrs[0].track_id.layer_id
        prev_width_layout = self.grid.get_track_width(prev_layer, warrs[0].track_id.width)
        for cur_layer in range(prev_layer + 1, top_layer):
            cur_width = self.grid.get_min_track_width(cur_layer, **em_specs,
                                                      bot_w=prev_width_layout)

            # make sure we can draw via to next layer up
            good = False
            while not good:
                try:
                    self.grid.get_via_extensions(cur_layer, cur_width, 1)
                    good = True
                except ValueError:
                    cur_width += 1

            cur_warrs = []
            for warr in warrs:
                tr = self.grid.coord_to_nearest_track(cur_layer, warr.middle)
                tid = TrackID(cur_layer, tr, width=cur_width)
                cur_warrs.append(self.connect_to_tracks(warr, tid, min_len_mode=0))

            if self.grid.get_direction(cur_layer) == 'x':
                self.connect_wires(cur_warrs)

            warrs = cur_warrs
            prev_width_layout = self.grid.get_track_width(cur_layer, cur_width)

        new_em_specs = em_specs.copy()
        for key in ['idc', 'iac_rms', 'iac_peak']:
            if key in new_em_specs:
                new_em_specs[key] *= num_seg

        top_width = self.grid.get_min_track_width(top_layer, **new_em_specs)
        tr = self.grid.coord_to_nearest_track(top_layer, warrs[0].middle)
        tid = TrackID(top_layer, tr, width=top_width)
        warr = self.connect_to_tracks(warrs, tid)
        label = name + ':' if name == 'VDD' or name == 'VSS' else name
        self.add_pin(name, warr, label=label, show=show_pins)