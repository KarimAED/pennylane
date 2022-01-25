# Copyright 2022 Xanadu Quantum Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Unit tests for the `pennylane.qcut` package.
"""
import numpy as np
import pennylane as qml
import pytest
from pennylane.transforms import qcut

with qml.tape.QuantumTape() as tape:
    qml.RX(0.432, wires=0)
    qml.RY(0.543, wires="a")
    qml.CNOT(wires=[0, "a"])
    qml.RZ(0.240, wires=0)
    qml.RZ(0.133, wires="a")
    qml.expval(qml.PauliZ(wires=[0]))


class TestTapeToGraph:
    """
    Tests conversion of tapes to graph representations that are amenable to
    partitioning algorithms for circuit cutting
    """

    def test_converted_graph_nodes(self):
        """
        Tests that the conversion of a tape gives a graph containing the
        expected nodes
        """

        g = qcut.tape_to_graph(tape)
        nodes = list(g.nodes)

        ops = tape.operations

        assert len(nodes) == len(ops) + len(tape.observables)
        for op, node in zip(ops, nodes[:-1]):
            assert op == node
        assert tape.observables[0] == nodes[-1].obs

    def test_converted_graph_edges(self):
        """
        Tests that the conversion of a tape gives a graph containing the
        expected edges
        """
        g = qcut.tape_to_graph(tape)
        edges = list(g.edges)

        num_wires_connecting_gates = 5
        assert len(edges) == num_wires_connecting_gates

        ops = tape.operations
        expected_edge_connections = [
            (ops[0], ops[2]),
            (ops[1], ops[2]),
            (ops[2], ops[3]),
            (ops[2], ops[4]),
            (ops[3], tape.observables[0]),
        ]

        for edge, expected_edge in zip(edges[:-1], expected_edge_connections[:-1]):
            assert (edge[0], edge[1]) == (expected_edge[0], expected_edge[1])
        assert (edges[-1][0], edges[-1][1].obs) == (
            expected_edge_connections[-1][0],
            expected_edge_connections[-1][1],
        )

    def test_node_order_attribute(self):
        """
        Tests that the converted nodes contain the correct order attirbute
        """

        g = qcut.tape_to_graph(tape)
        node_data = list(g.nodes(data=True))

        expected_node_order = [
            {"order": 0},
            {"order": 1},
            {"order": 2},
            {"order": 3},
            {"order": 4},
            {"order": 5},
        ]

        for data, expected_order in zip(node_data, expected_node_order):
            assert data[-1] == expected_order

    def test_edge_wire_attribute(self):
        """
        Tests that the converted edges contain the correct wire attirbute
        """

        g = qcut.tape_to_graph(tape)
        edge_data = list(g.edges(data=True))

        expected_edge_wires = [{"wire": 0}, {"wire": "a"}, {"wire": 0}, {"wire": "a"}, {"wire": 0}]

        for data, expected_wire in zip(edge_data, expected_edge_wires):
            assert data[-1] == expected_wire

    @pytest.mark.parametrize(
        "obs,expected_obs",
        [
            (
                qml.PauliZ(0) @ qml.PauliZ(2),
                [qml.expval(qml.PauliZ(wires=[0])), qml.expval(qml.PauliZ(wires=[2]))],
            ),
            (
                qml.Projector([0, 1], wires=[0, 1]),
                [qml.expval(qml.Projector([0, 1], wires=[0, 1]))],
            ),
            (
                qml.Hamiltonian([1, 2], [qml.PauliZ(1), qml.PauliZ(2) @ qml.PauliX(0)]),
                [
                    qml.expval(
                        qml.Hamiltonian([1, 2], [qml.PauliZ(1), qml.PauliZ(2) @ qml.PauliX(0)])
                    )
                ],
            ),
            (
                qml.Hermitian(np.array([[1, 0], [0, -1]]), wires=[0]),
                [qml.expval(qml.Hermitian(np.array([[1, 0], [0, -1]]), wires=[0]))],
            ),
            (
                qml.Projector([0, 1], wires=[0, 1]) @ qml.Projector([1, 0], wires=[0, 2]),
                [
                    qml.expval(qml.Projector([0, 1], wires=[0, 1])),
                    qml.expval(qml.Projector([1, 0], wires=[0, 2])),
                ],
            ),
        ],
    )
    def test_observable_conversion(self, obs, expected_obs):
        """
        Tests that a variety of observables in a tape are correctly converted to
        observables contained within the graph nodes
        """

        with qml.tape.QuantumTape() as tape:
            qml.RX(0.432, wires=0)
            qml.RY(0.543, wires=2)
            qml.CNOT(wires=[0, 1])
            qml.RZ(0.240, wires=0)
            qml.RZ(0.133, wires=1)
            qml.expval(obs)

        g = qcut.tape_to_graph(tape)
        nodes = list(g.nodes)

        node_observables = [node for node in nodes if hasattr(node, "return_type")]

        for node_obs, exp_obs in zip(node_observables, expected_obs):
            assert node_obs.wires == exp_obs.wires
            assert node_obs.obs.name == exp_obs.obs.name

    @pytest.mark.parametrize(
        "measurement,expected_measurement",
        [
            (qml.expval(qml.PauliZ(wires=[0])), "Expectation"),
            (qml.sample(qml.PauliZ(wires=[0])), "Sample"),
            (qml.var(qml.PauliZ(wires=[0])), "Variance"),
            (qml.probs(wires=0), "Probability"),
            (qml.state(), "State"),
            (qml.density_matrix([0]), "State"),
        ],
    )
    def test_measurement_conversion(self, measurement, expected_measurement):
        """
        Tests that measurements are correctly converted
        """

        with qml.tape.QuantumTape() as tape:
            qml.RX(0.432, wires=0)
            qml.RY(0.543, wires=2)
            qml.CNOT(wires=[0, 1])
            qml.RZ(0.240, wires=0)
            qml.RZ(0.133, wires=1)
            qml.apply(measurement)

        g = qcut.tape_to_graph(tape)
        nodes = list(g.nodes)

        node_observables = [node for node in nodes if hasattr(node, "return_type")]

        assert node_observables[0].return_type.name == expected_measurement

    @pytest.mark.parametrize(
        "prep,expected_prep",
        [
            (
                qml.BasisState(np.array([1, 1]), wires=range(2)),
                [qml.PauliX(wires=[0]), qml.PauliX(wires=[1])],
            ),
            (
                qml.QubitStateVector(np.array([1, 0, 0, 0]), wires=range(2)),
                [qml.CNOT(wires=[0, 1]), qml.CNOT(wires=[0, 1])],
            ),
            # (qml.QubitDensityMatrix(np.zeros((2 ** 2, 2 ** 2)), wires=[0, 1]), "?"), #Broken
        ],
    )
    def test_state_preparation(self, prep, expected_prep):
        """
        Tests that state preparation over mutliple wires are represented by
        the individual operations
        """

        with qml.tape.QuantumTape() as tape:
            qml.apply(prep)
            qml.RX(0.432, wires=0)
            qml.RY(0.543, wires=2)

        g = qcut.tape_to_graph(tape)
        nodes = list(g.nodes)

        node_preps = nodes[:2]
        for node_prep, expected_prep in zip(node_preps, expected_prep):
            assert node_prep.wires == expected_prep.wires
            assert node_prep.name == expected_prep.name


class TestReplaceWireCut:
    """
    Tests that the replacement of WireCut operation with MeasureNode and
    PrepareNode
    """

    def test_single_wire_cut_replaced(self):
        """
        Tests that a single WireCut operator is replaced with a MeasureNode and
        a PrepareNode with the correct order
        """

        wire_cut_num = 1

        with qml.tape.QuantumTape() as tape:
            qml.RX(0.432, wires=0)
            qml.RY(0.543, wires=1)
            qml.CNOT(wires=[0, 1])
            qml.RZ(0.240, wires=0)
            qml.RZ(0.133, wires=1)
            qml.WireCut(wires=wire_cut_num)
            qml.CNOT(wires=[1, 2])
            qml.RX(0.432, wires=1)
            qml.RY(0.543, wires=2)
            qml.expval(qml.PauliZ(wires=[0]))

        g = qcut.tape_to_graph(tape)
        node_data = list(g.nodes(data=True))

        wire_cut_order = None
        for op, order in node_data:
            if op.name == "WireCut":
                wire_cut_order = order

        qcut.replace_wire_cut_nodes(g)
        new_node_data = list(g.nodes(data=True))
        op_names = [op.name for op, order in new_node_data]

        assert "WireCut" not in op_names
        assert "MeasureNode" in op_names
        assert "PrepareNode" in op_names

        for op, order in new_node_data:
            if op.name == "MeasureNode":
                assert op.wires.tolist() == [wire_cut_num]
                assert order == wire_cut_order
            elif op.name == "PrepareNode":
                assert op.wires.tolist() == [wire_cut_num]
                assert order["order"] == wire_cut_order["order"] + 0.5

    def test_multiple_wire_cuts_replaced(self):
        """
        Tests that all WireCut operators are replaced with MeasureNodes and
        PrepareNodes with the correct order
        """

        wire_cut_1 = 0
        wire_cut_2 = "a"
        wire_cut_3 = 2
        wire_cut_num = [wire_cut_1, wire_cut_2, wire_cut_3]

        with qml.tape.QuantumTape() as tape:
            qml.RX(0.432, wires=0)
            qml.RY(0.543, wires="a")
            qml.WireCut(wires=wire_cut_1)
            qml.CNOT(wires=[0, "a"])
            qml.RZ(0.240, wires=0)
            qml.RZ(0.133, wires="a")
            qml.WireCut(wires=wire_cut_2)
            qml.CNOT(wires=["a", 2])
            qml.RX(0.432, wires="a")
            qml.WireCut(wires=wire_cut_3)
            qml.CNOT(wires=[2, 3])
            qml.RY(0.543, wires=2)
            qml.RZ(0.876, wires=3)
            qml.expval(qml.PauliZ(wires=[0]))

        g = qcut.tape_to_graph(tape)
        node_data = list(g.nodes(data=True))

        wire_cut_order = [order for op, order in node_data if op.name == "WireCut"]

        qcut.replace_wire_cut_nodes(g)
        new_node_data = list(g.nodes(data=True))
        op_names = [op.name for op, order in new_node_data]

        assert "WireCut" not in op_names
        assert op_names.count("MeasureNode") == 3
        assert op_names.count("PrepareNode") == 3

        measure_counter = prepare_counter = 0

        for op, order in new_node_data:
            if op.name == "MeasureNode":
                assert op.wires.tolist() == [wire_cut_num[measure_counter]]
                assert order == wire_cut_order[measure_counter]
                measure_counter += 1
            elif op.name == "PrepareNode":
                assert op.wires.tolist() == [wire_cut_num[prepare_counter]]
                assert order["order"] == wire_cut_order[prepare_counter]["order"] + 0.5
                prepare_counter += 1

    def test_successor_and_predecessor(self):
        """
        Tests the successor of the MeasureNode is the PrepareNode and the
        predecessor of the PrepareNode is the MeasureNode
        """
        wire_cut_num = 1

        with qml.tape.QuantumTape() as tape:
            qml.RX(0.432, wires=0)
            qml.CNOT(wires=[0, 1])
            qml.RZ(0.133, wires=1)
            qml.WireCut(wires=wire_cut_num)
            qml.CNOT(wires=[1, 2])
            qml.RY(0.543, wires=2)
            qml.expval(qml.PauliZ(wires=[0]))

        g = qcut.tape_to_graph(tape)
        qcut.replace_wire_cut_nodes(g)

        nodes = list(g.nodes)

        for node in nodes:
            if node.name == "MeasureNode":
                succ = list(g.succ[node])[0]
                assert succ.name == "PrepareNode"
            if node.name == "PrepareNode":
                pred = list(g.pred[node])[0]
                assert pred.name == "MeasureNode"
