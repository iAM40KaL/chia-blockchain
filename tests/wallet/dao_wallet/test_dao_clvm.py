from __future__ import annotations

import pytest

# mypy: ignore-errors
from clvm.casts import int_to_bytes

from chia.types.blockchain_format.coin import Coin
from chia.types.blockchain_format.program import INFINITE_COST, Program
from chia.types.blockchain_format.sized_bytes import bytes32
from chia.types.condition_opcodes import ConditionOpcode
from chia.util.condition_tools import conditions_dict_for_solution
from chia.util.hash import std_hash
from chia.util.ints import uint64
from chia.wallet.cat_wallet.cat_utils import CAT_MOD
from chia.wallet.puzzles.load_clvm import load_clvm
from chia.wallet.singleton import create_singleton_puzzle_hash

CAT_MOD_HASH: bytes32 = CAT_MOD.get_tree_hash()
SINGLETON_MOD: Program = load_clvm("singleton_top_layer_v1_1.clsp")
SINGLETON_MOD_HASH: bytes32 = SINGLETON_MOD.get_tree_hash()
SINGLETON_LAUNCHER: Program = load_clvm("singleton_launcher.clsp")
SINGLETON_LAUNCHER_HASH: bytes32 = SINGLETON_LAUNCHER.get_tree_hash()
DAO_LOCKUP_MOD: Program = load_clvm("dao_lockup.clsp")
DAO_LOCKUP_MOD_HASH: bytes32 = DAO_LOCKUP_MOD.get_tree_hash()
DAO_PROPOSAL_TIMER_MOD: Program = load_clvm("dao_proposal_timer.clsp")
DAO_PROPOSAL_TIMER_MOD_HASH: bytes32 = DAO_PROPOSAL_TIMER_MOD.get_tree_hash()
DAO_PROPOSAL_MOD: Program = load_clvm("dao_proposal.clsp")
DAO_PROPOSAL_MOD_HASH: bytes32 = DAO_PROPOSAL_MOD.get_tree_hash()
DAO_PROPOSAL_VALIDATOR_MOD: Program = load_clvm("dao_proposal_validator.clsp")
DAO_PROPOSAL_VALIDATOR_MOD_HASH: bytes32 = DAO_PROPOSAL_VALIDATOR_MOD.get_tree_hash()
DAO_TREASURY_MOD: Program = load_clvm("dao_treasury.clsp")
DAO_TREASURY_MOD_HASH: bytes32 = DAO_TREASURY_MOD.get_tree_hash()
SPEND_P2_SINGLETON_MOD: Program = load_clvm("dao_spend_p2_singleton_v2.clsp")
SPEND_P2_SINGLETON_MOD_HASH: bytes32 = SPEND_P2_SINGLETON_MOD.get_tree_hash()
DAO_FINISHED_STATE: Program = load_clvm("dao_finished_state.clsp")
DAO_FINISHED_STATE_HASH: bytes32 = DAO_FINISHED_STATE.get_tree_hash()
DAO_CAT_TAIL: Program = load_clvm("genesis_by_coin_id_or_singleton.clsp")
DAO_CAT_TAIL_HASH: bytes32 = DAO_CAT_TAIL.get_tree_hash()
P2_CONDITIONS_MOD: Program = load_clvm("p2_conditions_curryable.clsp")
P2_CONDITIONS_MOD_HASH: bytes32 = P2_CONDITIONS_MOD.get_tree_hash()
P2_SINGLETON_MOD: Program = load_clvm("p2_singleton_via_delegated_puzzle.clsp")
P2_SINGLETON_MOD_HASH: bytes32 = P2_SINGLETON_MOD.get_tree_hash()
P2_SINGLETON_AGGREGATOR_MOD: Program = load_clvm("p2_singleton_aggregator.clsp")
P2_SINGLETON_AGGREGATOR_MOD_HASH: bytes32 = P2_SINGLETON_AGGREGATOR_MOD.get_tree_hash()
DAO_UPDATE_MOD: Program = load_clvm("dao_update_proposal.clsp")
DAO_UPDATE_MOD_HASH: bytes32 = DAO_UPDATE_MOD.get_tree_hash()


def test_finished_state() -> None:
    """
    Once a proposal has closed, it becomes a 'beacon' singleton which announces its proposal ID. This is referred to as the finished state and is used to confirm that a proposal has closed in order to release voting CATs from the lockup puzzle.
    """
    proposal_id: Program = Program.to("proposal_id").get_tree_hash()
    singleton_struct: Program = Program.to(
        (SINGLETON_MOD.get_tree_hash(), (proposal_id, SINGLETON_LAUNCHER.get_tree_hash()))
    )
    finished_inner_puz = DAO_FINISHED_STATE.curry(singleton_struct, DAO_FINISHED_STATE_HASH)
    finished_full_puz = SINGLETON_MOD.curry(singleton_struct, finished_inner_puz)
    inner_sol = Program.to([1])

    conds = finished_inner_puz.run(inner_sol).as_python()
    assert conds[0][1] == finished_full_puz.get_tree_hash()
    assert conds[2][1] == finished_inner_puz.get_tree_hash()

    lineage = Program.to([proposal_id, finished_inner_puz.get_tree_hash(), 1])
    full_sol = Program.to([lineage, 1, inner_sol])

    conds = conditions_dict_for_solution(finished_full_puz, full_sol, INFINITE_COST)
    assert conds[ConditionOpcode.ASSERT_MY_PUZZLEHASH][0].vars[0] == finished_full_puz.get_tree_hash()
    assert conds[ConditionOpcode.CREATE_COIN][0].vars[0] == finished_full_puz.get_tree_hash()


def test_proposal() -> None:
    """
    This test covers the three paths for closing a proposal:
    - Close a passed proposal
    - Close a failed proposal
    - Self-destruct a broken proposal
    """
    proposal_pass_percentage: uint64 = uint64(5100)
    CAT_TAIL_HASH: Program = Program.to("tail").get_tree_hash()
    treasury_id: Program = Program.to("treasury").get_tree_hash()
    singleton_id: Program = Program.to("singleton_id").get_tree_hash()
    singleton_struct: Program = Program.to(
        (SINGLETON_MOD.get_tree_hash(), (singleton_id, SINGLETON_LAUNCHER.get_tree_hash()))
    )
    self_destruct_time = 1000  # number of blocks
    oracle_spend_delay = 10
    active_votes_list = [0xFADEDDAB]  # are the the ids of previously voted on proposals?
    acs: Program = Program.to(1)
    acs_ph: bytes32 = acs.get_tree_hash()

    dao_lockup_self = DAO_LOCKUP_MOD.curry(
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        DAO_FINISHED_STATE_HASH,
        CAT_MOD_HASH,
        CAT_TAIL_HASH,
    )

    proposal_curry_one = DAO_PROPOSAL_MOD.curry(
        DAO_PROPOSAL_TIMER_MOD_HASH,
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        CAT_MOD_HASH,
        DAO_FINISHED_STATE_HASH,
        DAO_TREASURY_MOD_HASH,
        dao_lockup_self.get_tree_hash(),
        CAT_TAIL_HASH,
        treasury_id,
    )

    # make a lockup puz for the dao cat
    lockup_puz = dao_lockup_self.curry(
        dao_lockup_self.get_tree_hash(),
        active_votes_list,
        acs,  # innerpuz
    )

    dao_cat_puz: Program = CAT_MOD.curry(CAT_MOD_HASH, CAT_TAIL_HASH, lockup_puz)
    dao_cat_puzhash: bytes32 = dao_cat_puz.get_tree_hash()

    # Test Voting
    current_yes_votes = 20
    current_total_votes = 100
    full_proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        singleton_id,
        acs_ph,
        current_yes_votes,
        current_total_votes,
    )

    vote_amount = 10
    vote_type = 1  # yes vote
    vote_coin_id = Program.to("vote_coin").get_tree_hash()
    # vote_amounts_or_proposal_validator_hash  ; The qty of "votes" to add or subtract. ALWAYS POSITIVE.
    # vote_info  ; vote_info is whether we are voting YES or NO. XXX rename vote_type?
    # vote_coin_ids_or_proposal_timelock_length  ; this is either the coin ID we're taking a vote from
    # previous_votes_or_pass_margin  ; this is the active votes of the lockup we're communicating with
    # ; OR this is what percentage of the total votes must be YES - represented as an integer from 0 to 10,000 - typically this is set at 5100 (51%)
    # lockup_innerpuzhashes_or_attendance_required  ; this is either the innerpuz of the locked up CAT we're taking a vote from OR
    # ; the attendance required - the percentage of the current issuance which must have voted represented as 0 to 10,000 - this is announced by the treasury
    # innerpuz_reveal  ; this is only added during the first vote
    # soft_close_length  ; revealed by the treasury - 0 in add vote case
    # self_destruct_time  ; revealed by the treasury
    # oracle_spend_delay  ; used to recreate the treasury
    # self_destruct_flag  ; if not 0, do the self-destruct spend
    # my_amount
    solution: Program = Program.to(
        [
            [vote_amount],  # vote amounts
            vote_type,  # vote type (yes)
            [vote_coin_id],  # vote coin ids
            [active_votes_list],  # previous votes
            [acs_ph],  # lockup inner puz hash
            0,  # inner puz reveal
            0,  # soft close len
            self_destruct_time,
            oracle_spend_delay,
            0,
            1,
        ]
    )

    # Run the proposal and check its conditions
    conditions = conditions_dict_for_solution(full_proposal, solution, INFINITE_COST)

    # Puzzle Announcement of vote_coin_ids
    assert bytes32(conditions[ConditionOpcode.CREATE_PUZZLE_ANNOUNCEMENT][0].vars[0]) == vote_coin_id

    # Assert puzzle announcement from dao_cat of proposal_id and all vote details
    apa_msg = Program.to([singleton_id, vote_amount, vote_type, vote_coin_id]).get_tree_hash()
    assert conditions[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT][0].vars[0] == std_hash(dao_cat_puzhash + apa_msg)

    # Check that the proposal recreates itself with updated vote amounts
    next_proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        singleton_id,
        acs_ph,
        current_yes_votes + vote_amount,
        current_total_votes + vote_amount,
    )
    assert bytes32(conditions[ConditionOpcode.CREATE_COIN][0].vars[0]) == next_proposal.get_tree_hash()
    assert conditions[ConditionOpcode.CREATE_COIN][0].vars[1] == int_to_bytes(1)

    # Test Launch
    current_yes_votes = 0
    current_total_votes = 0
    launch_proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        singleton_id,
        acs_ph,
        current_yes_votes,
        current_total_votes,
    )
    vote_amount = 10
    vote_type = 1  # yes vote
    vote_coin_id = Program.to("vote_coin").get_tree_hash()
    solution: Program = Program.to(
        [
            [vote_amount],  # vote amounts
            vote_type,  # vote type (yes)
            [vote_coin_id],  # vote coin ids
            # TODO: Check whether previous votes should be 0 in the first spend since
            # proposal looks at (f previous_votes) during loop_over_vote_coins
            [0],  # previous votes
            [acs_ph],  # lockup inner puz hash
            acs,  # inner puz reveal
            0,  # soft close len
            self_destruct_time,
            oracle_spend_delay,
            0,
            1,
        ]
    )
    # Run the proposal and check its conditions
    conditions = conditions_dict_for_solution(launch_proposal, solution, INFINITE_COST)
    # check that the timer is created
    timer_puz = DAO_PROPOSAL_TIMER_MOD.curry(
        proposal_curry_one.get_tree_hash(),
        singleton_struct,
    )
    timer_puzhash = timer_puz.get_tree_hash()
    assert conditions[ConditionOpcode.CREATE_COIN][1].vars[0] == timer_puzhash

    # Test exits

    # Test attempt to close a passing proposal
    current_yes_votes = 200
    current_total_votes = 350
    full_proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        singleton_id,
        acs_ph,
        current_yes_votes,
        current_total_votes,
    )
    attendance_required = 200
    proposal_timelock = 20
    soft_close_length = 5
    solution = Program.to(
        [
            Program.to("validator_hash").get_tree_hash(),
            0,
            # Program.to("receiver_hash").get_tree_hash(), # not needed anymore?
            proposal_timelock,
            proposal_pass_percentage,
            attendance_required,
            0,
            soft_close_length,
            self_destruct_time,
            oracle_spend_delay,
            0,
            1,
        ]
    )

    conds = conditions_dict_for_solution(full_proposal, solution, INFINITE_COST)

    # make a matching treasury puzzle for the APA
    treasury_inner: Program = DAO_TREASURY_MOD.curry(
        DAO_TREASURY_MOD_HASH,
        Program.to("validator_hash"),
        proposal_timelock,
        soft_close_length,
        attendance_required,
        proposal_pass_percentage,
        self_destruct_time,
        oracle_spend_delay,
    )
    treasury: Program = SINGLETON_MOD.curry(
        Program.to((SINGLETON_MOD_HASH, (treasury_id, SINGLETON_LAUNCHER_HASH))),
        treasury_inner,
    )
    treasury_puzhash = treasury.get_tree_hash()
    apa_msg = singleton_id

    timer_apa = std_hash(timer_puzhash + singleton_id)
    assert conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT][0].vars[0] == timer_apa
    assert conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT][1].vars[0] == std_hash(treasury_puzhash + apa_msg)

    # close a failed proposal
    full_proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        singleton_id,
        acs_ph,
        20,  # failing number of yes votes
        current_total_votes,
    )
    solution = Program.to(
        [
            Program.to("validator_hash").get_tree_hash(),
            0,
            # Program.to("receiver_hash").get_tree_hash(), # not needed anymore?
            proposal_timelock,
            proposal_pass_percentage,
            attendance_required,
            0,
            soft_close_length,
            self_destruct_time,
            oracle_spend_delay,
            0,
            1,
        ]
    )
    conds = conditions_dict_for_solution(full_proposal, solution, INFINITE_COST)
    apa_msg = int_to_bytes(0)
    assert conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT][1].vars[0] == std_hash(treasury_puzhash + apa_msg)
    assert conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT][0].vars[0] == timer_apa

    finished_puz = DAO_FINISHED_STATE.curry(singleton_struct, DAO_FINISHED_STATE_HASH)
    assert conds[ConditionOpcode.CREATE_COIN][0].vars[0] == finished_puz.get_tree_hash()

    # self destruct a proposal
    attendance_required = 200
    solution = Program.to(
        [
            Program.to("validator_hash").get_tree_hash(),
            0,
            # Program.to("receiver_hash").get_tree_hash(), # not needed anymore?
            proposal_timelock,
            proposal_pass_percentage,
            attendance_required,
            0,
            soft_close_length,
            self_destruct_time,
            oracle_spend_delay,
            1,
            1,
        ]
    )
    conds = conditions_dict_for_solution(full_proposal, solution, INFINITE_COST)
    assert conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT][0].vars[0] == std_hash(treasury_puzhash + apa_msg)
    assert conds[ConditionOpcode.CREATE_COIN][0].vars[0] == finished_puz.get_tree_hash()


def test_proposal_timer() -> None:
    """
    The timer puzzle is created at the same time as a proposal, and enforces a relative time condition on proposals
    The closing time is passed in via the timer solution and confirmed via announcement from the proposal.
    It creates/asserts announcements to pair it with the finishing spend of a proposal.
    The timer puzzle only has one spend path so there is only one test case for this puzzle.
    """
    CAT_TAIL_HASH: Program = Program.to("tail").get_tree_hash()
    treasury_id: Program = Program.to("treasury").get_tree_hash()
    singleton_id: Program = Program.to("singleton_id").get_tree_hash()
    singleton_struct: Program = Program.to(
        (SINGLETON_MOD.get_tree_hash(), (singleton_id, SINGLETON_LAUNCHER.get_tree_hash()))
    )
    dao_lockup_self = DAO_LOCKUP_MOD.curry(
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        DAO_FINISHED_STATE_HASH,
        CAT_MOD_HASH,
        CAT_TAIL_HASH,
    )

    proposal_curry_one = DAO_PROPOSAL_MOD.curry(
        DAO_PROPOSAL_TIMER_MOD_HASH,
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        CAT_MOD_HASH,
        DAO_FINISHED_STATE_HASH,
        DAO_TREASURY_MOD_HASH,
        dao_lockup_self.get_tree_hash(),
        CAT_TAIL_HASH,
        treasury_id,
    )

    proposal_timer_full: Program = DAO_PROPOSAL_TIMER_MOD.curry(
        proposal_curry_one.get_tree_hash(),
        singleton_struct,
    )

    timelock = int_to_bytes(101)
    parent_parent_id = Program.to("parent_parent").get_tree_hash()
    parent_amount = 2000
    solution: Program = Program.to(
        [
            140,  # yes votes
            180,  # total votes
            Program.to(1).get_tree_hash(),  # proposal innerpuz
            timelock,
            parent_parent_id,
            parent_amount,
        ]
    )
    # run the timer puzzle.
    conds: Program = conditions_dict_for_solution(proposal_timer_full, solution, INFINITE_COST)
    assert len(conds) == 4

    # Validate the output conditions
    # Check the timelock is present
    assert conds[ConditionOpcode.ASSERT_HEIGHT_RELATIVE][0].vars[0] == timelock
    # Check the proposal id is announced by the timer puz
    assert conds[ConditionOpcode.CREATE_PUZZLE_ANNOUNCEMENT][0].vars[0] == singleton_id
    # Check the proposal puz announces the timelock
    expected_proposal_puzhash: Program = create_singleton_puzzle_hash(
        proposal_curry_one.curry(
            proposal_curry_one.get_tree_hash(), singleton_id, Program.to(1).get_tree_hash(), 140, 180
        ).get_tree_hash(),
        singleton_id,
    )
    assert conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT][0].vars[0] == std_hash(
        expected_proposal_puzhash + timelock
    )
    # Check the parent is a proposal
    expected_parent_puzhash: Program = create_singleton_puzzle_hash(
        proposal_curry_one.curry(
            proposal_curry_one.get_tree_hash(),
            singleton_id,
            Program.to(1).get_tree_hash(),
            0,
            0,
        ).get_tree_hash(),
        singleton_id,
    )
    parent_id = std_hash(parent_parent_id + expected_parent_puzhash + int_to_bytes(parent_amount))
    assert conds[ConditionOpcode.ASSERT_MY_PARENT_ID][0].vars[0] == parent_id


def test_validator() -> None:
    """
    The proposal validator is run by the treasury when a passing proposal is closed.
    Its main purpose is to check that the proposal's vote amounts adehere to the DAO rules contained in the treasury (which are passed in from the treasury as Truth values).
    It creates a puzzle announcement of the proposal ID, that the proposal itself asserts.
    It also spends the value held in the proposal to the excess payout puzhash.

    The test cases covered are:
    - Executing a spend proposal in which the validator executes the spend of a 'spend_p2_singleton` coin. This is just a proposal that spends some the treasury
    - Executing an update proposal that changes the DAO rules.
    """
    # Setup the treasury
    treasury_id: Program = Program.to("treasury_id").get_tree_hash()
    treasury_struct: Program = Program.to((SINGLETON_MOD_HASH, (treasury_id, SINGLETON_LAUNCHER_HASH)))

    # Setup the proposal
    proposal_id: Program = Program.to("proposal_id").get_tree_hash()
    proposal_struct: Program = Program.to((SINGLETON_MOD.get_tree_hash(), (proposal_id, SINGLETON_LAUNCHER_HASH)))
    CAT_TAIL_HASH: Program = Program.to("tail").get_tree_hash()
    acs: Program = Program.to(1)
    acs_ph: bytes32 = acs.get_tree_hash()

    p2_singleton = P2_SINGLETON_MOD.curry(treasury_struct, P2_SINGLETON_AGGREGATOR_MOD)
    p2_singleton_puzhash = p2_singleton.get_tree_hash()
    parent_id = Program.to("parent").get_tree_hash()
    locked_amount = 100000
    spend_amount = 1100
    conditions = [[51, 0xDABBAD00, 1000], [51, 0xCAFEF00D, 100]]

    # Setup the validator
    minimum_amt = 1
    excess_puzhash = bytes32(b"1" * 32)
    dao_lockup_self = DAO_LOCKUP_MOD.curry(
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        DAO_FINISHED_STATE_HASH,
        CAT_MOD_HASH,
        CAT_TAIL_HASH,
    )

    proposal_curry_one = DAO_PROPOSAL_MOD.curry(
        DAO_PROPOSAL_TIMER_MOD_HASH,
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        CAT_MOD_HASH,
        DAO_FINISHED_STATE_HASH,
        DAO_TREASURY_MOD_HASH,
        dao_lockup_self.get_tree_hash(),
        CAT_TAIL_HASH,
        treasury_id,
    )
    proposal_validator = DAO_PROPOSAL_VALIDATOR_MOD.curry(
        treasury_struct,
        proposal_curry_one.get_tree_hash(),
        minimum_amt,
        excess_puzhash,
    )

    # Can now create the treasury inner puz
    treasury_inner = DAO_TREASURY_MOD.curry(
        DAO_TREASURY_MOD_HASH,
        proposal_validator,
        10,  # proposal len
        5,  # soft close
        1000,  # attendance
        5100,  # pass margin
        20,  # self_destruct len
        3,  # oracle delay
    )

    # Setup the spend_p2_singleton (proposal inner puz)
    spend_p2_singleton = SPEND_P2_SINGLETON_MOD.curry(
        treasury_struct, CAT_MOD_HASH, conditions, [], p2_singleton_puzhash  # tailhash conds
    )
    spend_p2_singleton_puzhash = spend_p2_singleton.get_tree_hash()

    parent_amt_list = [[parent_id, locked_amount]]
    cat_parent_amt_list = []
    spend_p2_singleton_solution = Program.to([parent_amt_list, cat_parent_amt_list, treasury_inner.get_tree_hash()])

    output_conds = spend_p2_singleton.run(spend_p2_singleton_solution)

    proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        proposal_id,
        spend_p2_singleton_puzhash,
        950,
        1200,
    )
    full_proposal = SINGLETON_MOD.curry(proposal_struct, proposal)
    proposal_amt = 10
    proposal_coin_id = Coin(parent_id, full_proposal.get_tree_hash(), proposal_amt).name()
    solution = Program.to(
        [
            1000,
            5100,
            [proposal_coin_id, spend_p2_singleton_puzhash, 0],
            [proposal_id, 1200, 950, parent_id, proposal_amt],
            output_conds,
        ]
    )

    conds: Program = proposal_validator.run(solution)
    assert len(conds.as_python()) == 7 + len(conditions)

    # test update
    proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        proposal_id,
        acs_ph,
        950,
        1200,
    )
    full_proposal = SINGLETON_MOD.curry(proposal_struct, proposal)
    proposal_coin_id = Coin(parent_id, full_proposal.get_tree_hash(), proposal_amt).name()
    solution = Program.to(
        [
            1000,
            5100,
            [proposal_coin_id, acs_ph, 0],
            [proposal_id, 1200, 950, parent_id, proposal_amt],
            [[51, 0xCAFEF00D, spend_amount]],
        ]
    )
    conds: Program = proposal_validator.run(solution)
    assert len(conds.as_python()) == 3

    return


def test_merge_p2_singleton() -> None:
    """
    The treasury funds are held by p2_singleton_via_delegated puzzles. Because a DAO can have a large number of these coins, it's possible to merge them together without requiring a treasury spend.
    There are two cases tested:
    - For the merge coins that do not create the single output coin, and
    - For the coin that does create the output.
    """
    # Setup a singleton struct
    singleton_inner: Program = Program.to(1)
    singleton_id: Program = Program.to("singleton_id").get_tree_hash()
    singleton_struct: Program = Program.to((SINGLETON_MOD_HASH, (singleton_id, SINGLETON_LAUNCHER_HASH)))

    # Setup p2_singleton_via_delegated puz
    my_id = Program.to("my_id").get_tree_hash()
    p2_singleton = P2_SINGLETON_MOD.curry(singleton_struct, P2_SINGLETON_AGGREGATOR_MOD)
    my_puzhash = p2_singleton.get_tree_hash()

    # Spend to delegated puz
    delegated_puz = Program.to(1)
    delegated_sol = Program.to([[51, 0xCAFEF00D, 300]])
    solution = Program.to([0, singleton_inner.get_tree_hash(), delegated_puz, delegated_sol, my_id])
    conds = conditions_dict_for_solution(p2_singleton, solution, INFINITE_COST)
    apa = std_hash(
        SINGLETON_MOD.curry(singleton_struct, singleton_inner).get_tree_hash()
        + Program.to([my_id, delegated_puz.get_tree_hash()]).get_tree_hash()
    )
    assert len(conds) == 4
    assert conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT][0].vars[0] == apa
    assert conds[ConditionOpcode.CREATE_COIN][0].vars[1] == int_to_bytes(300)

    # Merge Spend (not output creator)
    merge_sol = Program.to([[my_id, my_puzhash, 300, 0]])
    conds = conditions_dict_for_solution(p2_singleton, merge_sol, INFINITE_COST)
    assert len(conds) == 2
    assert conds[ConditionOpcode.ASSERT_MY_PUZZLEHASH][0].vars[0] == my_puzhash
    assert conds[ConditionOpcode.CREATE_COIN_ANNOUNCEMENT][0].vars[0] == int_to_bytes(0)

    # Merge Spend (output creator)
    fake_parent_id = Program.to("fake_parent").get_tree_hash()
    merged_coin_id = Coin(fake_parent_id, my_puzhash, 200).name()
    merge_sol = Program.to([[my_id, my_puzhash, 100, [[fake_parent_id, my_puzhash, 200]]]])
    conds = conditions_dict_for_solution(p2_singleton, merge_sol, INFINITE_COST)
    assert len(conds) == 5
    assert conds[ConditionOpcode.ASSERT_COIN_ANNOUNCEMENT][0].vars[0] == Program.to([merged_coin_id, 0]).get_tree_hash()
    assert conds[ConditionOpcode.CREATE_COIN][0].vars[1] == int_to_bytes(300)
    return


def test_treasury() -> None:
    """
    The treasury has two spend paths:
    - Proposal Path: when a proposal is being closed the treasury spend runs the validator and the actual proposed code (if passed)
    - Oracle Path: The treasury can make announcements about itself that are used to close invalid proposals
    """
    # Setup the treasury
    treasury_id: Program = Program.to("treasury_id").get_tree_hash()
    treasury_struct: Program = Program.to((SINGLETON_MOD_HASH, (treasury_id, SINGLETON_LAUNCHER_HASH)))
    CAT_TAIL_HASH: Program = Program.to("tail").get_tree_hash()

    proposal_id: Program = Program.to("singleton_id").get_tree_hash()
    proposal_struct: Program = Program.to((SINGLETON_MOD_HASH, (proposal_id, SINGLETON_LAUNCHER_HASH)))
    p2_singleton = P2_SINGLETON_MOD.curry(treasury_struct, P2_SINGLETON_AGGREGATOR_MOD)
    p2_singleton_puzhash = p2_singleton.get_tree_hash()
    parent_id = Program.to("parent").get_tree_hash()
    locked_amount = 100000
    oracle_spend_delay = 10
    self_destruct_time = 1000
    proposal_length = 40
    soft_close_length = 5
    attendance = 1000
    pass_margin = 5100
    conditions = [[51, 0xDABBAD00, 1000], [51, 0xCAFEF00D, 100]]

    # Setup the validator
    minimum_amt = 1
    excess_puzhash = bytes32(b"1" * 32)
    dao_lockup_self = DAO_LOCKUP_MOD.curry(
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        DAO_FINISHED_STATE_HASH,
        CAT_MOD_HASH,
        CAT_TAIL_HASH,
    )

    proposal_curry_one = DAO_PROPOSAL_MOD.curry(
        DAO_PROPOSAL_TIMER_MOD_HASH,
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        CAT_MOD_HASH,
        DAO_FINISHED_STATE_HASH,
        DAO_TREASURY_MOD_HASH,
        dao_lockup_self.get_tree_hash(),
        CAT_TAIL_HASH,
        treasury_id,
    )
    proposal_validator = DAO_PROPOSAL_VALIDATOR_MOD.curry(
        treasury_struct,
        proposal_curry_one.get_tree_hash(),
        minimum_amt,
        excess_puzhash,
    )

    # Can now create the treasury inner puz
    treasury_inner = DAO_TREASURY_MOD.curry(
        DAO_TREASURY_MOD_HASH,
        proposal_validator,
        proposal_length,
        soft_close_length,
        attendance,
        pass_margin,
        self_destruct_time,
        oracle_spend_delay,
    )

    # Setup the spend_p2_singleton (proposal inner puz)
    spend_p2_singleton = SPEND_P2_SINGLETON_MOD.curry(
        treasury_struct, CAT_MOD_HASH, conditions, [], p2_singleton_puzhash  # tailhash conds
    )
    spend_p2_singleton_puzhash = spend_p2_singleton.get_tree_hash()

    parent_amt_list = [[parent_id, locked_amount]]
    cat_parent_amt_list = []
    spend_p2_singleton_solution = Program.to([parent_amt_list, cat_parent_amt_list, treasury_inner.get_tree_hash()])

    proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        proposal_id,
        spend_p2_singleton_puzhash,
        950,
        1200,
    )
    full_proposal = SINGLETON_MOD.curry(proposal_struct, proposal)

    # Oracle spend
    solution: Program = Program.to([0, 0, 0, 0, 0, treasury_struct])
    conds: Program = treasury_inner.run(solution)
    assert len(conds.as_python()) == 3

    # Proposal Spend
    proposal_amt = 10
    proposal_coin_id = Coin(parent_id, full_proposal.get_tree_hash(), proposal_amt).name()
    solution: Program = Program.to(
        [
            [proposal_coin_id, spend_p2_singleton_puzhash, 0, "s"],
            [proposal_id, 1200, 950, parent_id, proposal_amt],
            spend_p2_singleton,
            spend_p2_singleton_solution,
        ]
    )
    conds = treasury_inner.run(solution)
    assert len(conds.as_python()) == 9 + len(conditions)


def test_lockup() -> None:
    """
    The lockup puzzle tracks the voting records of DAO CATs. When a proposal is voted on the proposal ID is added to a list against which future votes are checked.
    This test checks the addition of new votes to the lockup, and that you can't re-vote on a proposal twice.
    """
    CAT_TAIL_HASH: Program = Program.to("tail").get_tree_hash()

    INNERPUZ = Program.to(1)
    previous_votes = [0xFADEDDAB]

    dao_lockup_self = DAO_LOCKUP_MOD.curry(
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        DAO_FINISHED_STATE_HASH,
        CAT_MOD_HASH,
        CAT_TAIL_HASH,
    )

    full_lockup_puz: Program = dao_lockup_self.curry(
        dao_lockup_self.get_tree_hash(),
        previous_votes,
        INNERPUZ,
    )
    my_id = Program.to("my_id").get_tree_hash()
    lockup_coin_amount = 20

    # Test adding vote
    new_proposal = 0xBADDADAB
    new_vote_list = [new_proposal, 0xFADEDDAB]
    child_puzhash = dao_lockup_self.curry(
        dao_lockup_self.get_tree_hash(),
        new_vote_list,
        INNERPUZ,
    ).get_tree_hash()
    message = Program.to([new_proposal, lockup_coin_amount, 1, my_id]).get_tree_hash()
    generated_conditions = [[51, child_puzhash, lockup_coin_amount], [62, message]]
    solution: Program = Program.to(
        [
            my_id,
            generated_conditions,
            20,
            new_proposal,
            INNERPUZ.get_tree_hash(),  # fake proposal curry vals
            1,
            20,
            child_puzhash,
            0,
        ]
    )
    conds: Program = full_lockup_puz.run(solution)
    assert len(conds.as_python()) == 6

    # Test Re-voting on same proposal fails
    new_proposal = 0xBADDADAB
    new_vote_list = [new_proposal, 0xBADDADAB]
    child_puzhash = dao_lockup_self.curry(
        dao_lockup_self.get_tree_hash(),
        new_vote_list,
        INNERPUZ,
    ).get_tree_hash()
    message = Program.to([new_proposal, lockup_coin_amount, 1, my_id]).get_tree_hash()
    generated_conditions = [[51, child_puzhash, lockup_coin_amount], [62, message]]
    revote_solution: Program = Program.to(
        [
            my_id,
            generated_conditions,
            20,
            new_proposal,
            INNERPUZ.get_tree_hash(),  # fake proposal curry vals
            1,
            20,
            child_puzhash,
            0,
        ]
    )
    with pytest.raises(ValueError) as e_info:
        conds: Program = full_lockup_puz.run(revote_solution)
    assert e_info.value.args[0] == "clvm raise"

    # Test vote removal
    solution = Program.to(
        [
            0,
            generated_conditions,
            20,
            [0xFADEDDAB],
            INNERPUZ.get_tree_hash(),
            0,
            0,
            0,
            0,
        ]
    )
    conds = full_lockup_puz.run(solution)
    assert len(conds.as_python()) == 3

    new_innerpuz = Program.to("new_inner")
    new_innerpuzhash = new_innerpuz.get_tree_hash()
    child_lockup = dao_lockup_self.curry(
        dao_lockup_self.get_tree_hash(),
        previous_votes,
        new_innerpuz,
    ).get_tree_hash()
    message = Program.to([0, 0, 0, my_id]).get_tree_hash()
    spend_conds = [[51, child_lockup, lockup_coin_amount], [62, message]]
    transfer_sol = Program.to(
        [
            my_id,
            spend_conds,
            lockup_coin_amount,
            0,
            INNERPUZ.get_tree_hash(),  # fake proposal curry vals
            0,
            0,
            INNERPUZ.get_tree_hash(),
            new_innerpuzhash,
        ]
    )
    conds = full_lockup_puz.run(transfer_sol)
    assert conds.at("rrrrfrf").as_atom() == child_lockup


def test_proposal_lifecycle() -> None:
    """
    This test covers the whole lifecycle of a proposal and treasury. It's main function is to check that the announcement pairs between treasury and proposal are accurate. It covers the spend proposal and update proposal types.
    """
    proposal_pass_percentage: uint64 = uint64(5100)
    attendance_required: uint64 = uint64(1000)
    proposal_timelock = 40
    soft_close_length = 5
    self_destruct_time = 1000
    CAT_TAIL_HASH: Program = Program.to("tail").get_tree_hash()
    oracle_spend_delay = 10

    # Setup the treasury
    treasury_id: Program = Program.to("treasury_id").get_tree_hash()
    treasury_singleton_struct: Program = Program.to((SINGLETON_MOD_HASH, (treasury_id, SINGLETON_LAUNCHER_HASH)))
    treasury_amount = 1

    # setup the p2_singleton
    p2_singleton = P2_SINGLETON_MOD.curry(treasury_singleton_struct, P2_SINGLETON_AGGREGATOR_MOD)
    p2_singleton_puzhash = p2_singleton.get_tree_hash()
    parent_id = Program.to("parent").get_tree_hash()
    locked_amount = 100000
    conditions = [[51, 0xDABBAD00, 1000], [51, 0xCAFEF00D, 100]]

    min_amt = 1
    excess_puzhash = bytes32(b"1" * 32)
    dao_lockup_self = DAO_LOCKUP_MOD.curry(
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        DAO_FINISHED_STATE_HASH,
        CAT_MOD_HASH,
        CAT_TAIL_HASH,
    )

    proposal_curry_one = DAO_PROPOSAL_MOD.curry(
        DAO_PROPOSAL_TIMER_MOD_HASH,
        SINGLETON_MOD_HASH,
        SINGLETON_LAUNCHER_HASH,
        CAT_MOD_HASH,
        DAO_FINISHED_STATE_HASH,
        DAO_TREASURY_MOD_HASH,
        dao_lockup_self.get_tree_hash(),
        CAT_TAIL_HASH,
        treasury_id,
    )
    proposal_validator = DAO_PROPOSAL_VALIDATOR_MOD.curry(
        treasury_singleton_struct,
        proposal_curry_one.get_tree_hash(),
        min_amt,
        excess_puzhash,
    )

    treasury_inner_puz: Program = DAO_TREASURY_MOD.curry(
        DAO_TREASURY_MOD_HASH,
        proposal_validator,
        proposal_timelock,
        soft_close_length,
        attendance_required,
        proposal_pass_percentage,
        self_destruct_time,
        oracle_spend_delay,
    )
    treasury_inner_puzhash = treasury_inner_puz.get_tree_hash()

    full_treasury_puz = SINGLETON_MOD.curry(treasury_singleton_struct, treasury_inner_puz)
    full_treasury_puzhash = full_treasury_puz.get_tree_hash()

    # Setup the spend_p2_singleton (proposal inner puz)
    spend_p2_singleton = SPEND_P2_SINGLETON_MOD.curry(
        treasury_singleton_struct, CAT_MOD_HASH, conditions, [], p2_singleton_puzhash  # tailhash conds
    )
    spend_p2_singleton_puzhash = spend_p2_singleton.get_tree_hash()

    parent_amt_list = [[parent_id, locked_amount]]
    cat_parent_amt_list = []
    spend_p2_singleton_solution = Program.to([parent_amt_list, cat_parent_amt_list, treasury_inner_puzhash])

    # Setup Proposal
    proposal_id: Program = Program.to("proposal_id").get_tree_hash()
    proposal_singleton_struct: Program = Program.to((SINGLETON_MOD_HASH, (proposal_id, SINGLETON_LAUNCHER_HASH)))

    current_votes = 1200
    yes_votes = 950
    proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        proposal_id,
        spend_p2_singleton_puzhash,
        yes_votes,
        current_votes,
    )
    full_proposal: Program = SINGLETON_MOD.curry(proposal_singleton_struct, proposal)
    full_proposal_puzhash: bytes32 = full_proposal.get_tree_hash()
    proposal_amt = 11
    proposal_coin_id = Coin(parent_id, full_proposal_puzhash, proposal_amt).name()

    treasury_solution: Program = Program.to(
        [
            [proposal_coin_id, spend_p2_singleton_puzhash, 0],
            [proposal_id, current_votes, yes_votes, parent_id, proposal_amt],
            spend_p2_singleton,
            spend_p2_singleton_solution,
        ]
    )

    proposal_solution = Program.to(
        [
            proposal_validator.get_tree_hash(),
            0,
            proposal_timelock,
            proposal_pass_percentage,
            attendance_required,
            0,
            soft_close_length,
            self_destruct_time,
            oracle_spend_delay,
            0,
            proposal_amt,
        ]
    )

    # lineage_proof my_amount inner_solution
    lineage_proof = [treasury_id, treasury_inner_puzhash, treasury_amount]
    full_treasury_solution = Program.to([lineage_proof, treasury_amount, treasury_solution])
    full_proposal_solution = Program.to([lineage_proof, proposal_amt, proposal_solution])

    # Run the puzzles
    treasury_conds: Program = conditions_dict_for_solution(full_treasury_puz, full_treasury_solution, INFINITE_COST)
    proposal_conds: Program = conditions_dict_for_solution(full_proposal, full_proposal_solution, INFINITE_COST)

    # Announcements
    treasury_aca = treasury_conds[ConditionOpcode.ASSERT_COIN_ANNOUNCEMENT][0].vars[0]
    proposal_cca = proposal_conds[ConditionOpcode.CREATE_COIN_ANNOUNCEMENT][0].vars[0]
    assert std_hash(proposal_coin_id + proposal_cca) == treasury_aca

    treasury_cpas = [
        std_hash(full_treasury_puzhash + cond.vars[0])
        for cond in treasury_conds[ConditionOpcode.CREATE_PUZZLE_ANNOUNCEMENT]
    ]
    proposal_apas = [cond.vars[0] for cond in proposal_conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT]]
    assert treasury_cpas[1] == proposal_apas[1]

    # Test Proposal to update treasury
    # Set up new treasury params
    new_proposal_pass_percentage: uint64 = uint64(2500)
    new_attendance_required: uint64 = uint64(500)
    new_proposal_timelock = 900
    new_soft_close_length = 10
    new_self_destruct_time = 1000
    new_oracle_spend_delay = 20

    update_proposal = DAO_UPDATE_MOD.curry(
        DAO_TREASURY_MOD_HASH,
        proposal_validator,
        new_proposal_timelock,
        new_soft_close_length,
        new_attendance_required,
        new_proposal_pass_percentage,
        new_self_destruct_time,
        new_oracle_spend_delay,
    )
    update_proposal_puzhash = update_proposal.get_tree_hash()
    update_proposal_sol = Program.to([])

    proposal: Program = proposal_curry_one.curry(
        proposal_curry_one.get_tree_hash(),
        proposal_id,
        update_proposal_puzhash,
        yes_votes,
        current_votes,
    )
    full_proposal: Program = SINGLETON_MOD.curry(proposal_singleton_struct, proposal)
    full_proposal_puzhash: bytes32 = full_proposal.get_tree_hash()
    proposal_coin_id = Coin(parent_id, full_proposal_puzhash, proposal_amt).name()

    treasury_solution: Program = Program.to(
        [
            [proposal_coin_id, update_proposal_puzhash, 0, "u"],
            [proposal_id, current_votes, yes_votes, parent_id, proposal_amt],
            update_proposal,
            update_proposal_sol,
        ]
    )

    proposal_solution = Program.to(
        [
            proposal_validator.get_tree_hash(),
            0,
            proposal_timelock,
            proposal_pass_percentage,
            attendance_required,
            0,
            soft_close_length,
            self_destruct_time,
            oracle_spend_delay,
            0,
            proposal_amt,
        ]
    )

    lineage_proof = [treasury_id, treasury_inner_puzhash, treasury_amount]
    full_treasury_solution = Program.to([lineage_proof, treasury_amount, treasury_solution])
    full_proposal_solution = Program.to([lineage_proof, proposal_amt, proposal_solution])

    treasury_conds: Program = conditions_dict_for_solution(full_treasury_puz, full_treasury_solution, INFINITE_COST)
    proposal_conds: Program = conditions_dict_for_solution(full_proposal, full_proposal_solution, INFINITE_COST)

    treasury_aca = treasury_conds[ConditionOpcode.ASSERT_COIN_ANNOUNCEMENT][0].vars[0]
    proposal_cca = proposal_conds[ConditionOpcode.CREATE_COIN_ANNOUNCEMENT][0].vars[0]
    assert std_hash(proposal_coin_id + proposal_cca) == treasury_aca

    treasury_cpas = [
        std_hash(full_treasury_puzhash + cond.vars[0])
        for cond in treasury_conds[ConditionOpcode.CREATE_PUZZLE_ANNOUNCEMENT]
    ]
    proposal_apas = [cond.vars[0] for cond in proposal_conds[ConditionOpcode.ASSERT_PUZZLE_ANNOUNCEMENT]]
    assert treasury_cpas[1] == proposal_apas[1]