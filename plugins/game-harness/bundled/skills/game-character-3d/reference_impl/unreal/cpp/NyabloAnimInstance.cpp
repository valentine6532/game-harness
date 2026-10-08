#include "NyabloAnimInstance.h"

#include "Animation/AnimNodeBase.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationPoseData.h"
#include "AnimationRuntime.h"

void UNyabloAnimInstance::Play(UAnimSequence* Anim, bool bLoop, float BlendTime, float StartTime, float Rate, float MaxTime)
{
	++PlayCount;
	if (!bCurFresh)
	{
		if (Prev.Anim && BlendLeft > 0.f)
		{
			// interrupting a fade: freeze what is on screen (the proxy copies its last drawn pose) and fade from that.
			// Picking either clip instead dropped the other one's visible share in one frame (10-21 % of height).
			Prev = FNyabloAnimSlot();
			Prev.Anim = Cur.Anim;                // only marks the slot as used; the snapshot pose is what is drawn
			Prev.RootOffset = PendingShift;      // capsule moved this frame after that pose was drawn
			bPrevIsSnapshot = true;
			++SnapshotRequest;
		}
		else
		{
			Prev = Cur;
			bPrevIsSnapshot = false;
		}
	}
	// else: a second Play before the first was ever shown (swing end -> idle -> queued swing, same tick): the fade
	// source stays what is on screen
	BlendTotal = BlendLeft = (Prev.Anim && BlendTime > 0.f) ? BlendTime : 0.f;
	Cur = FNyabloAnimSlot();
	Cur.Anim = Anim;
	Cur.Time = StartTime;
	Cur.Rate = Rate;
	Cur.bLoop = bLoop;
	Cur.MaxTime = MaxTime;
	bCurFresh = true;
}

void UNyabloAnimInstance::ShiftRoots(const FVector& Delta)
{
	Cur.RootOffset += Delta;
	Prev.RootOffset += Delta;
	PendingShift += Delta;
}

void UNyabloAnimInstance::Advance(FNyabloAnimSlot& Slot, float DeltaSeconds)
{
	if (!Slot.Anim)
	{
		return;
	}
	const float Length = FMath::Max(Slot.Anim->GetPlayLength(), 0.001f);
	Slot.Time += DeltaSeconds * Slot.Rate;
	Slot.Time = Slot.bLoop ? FMath::Fmod(FMath::Fmod(Slot.Time, Length) + Length, Length)
		: FMath::Clamp(Slot.Time, 0.f, Slot.MaxTime > 0.f ? FMath::Min(Slot.MaxTime, Length) : Length);
}

void UNyabloAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);
	PendingShift = FVector::ZeroVector;   // the proxy has copied this frame's state (PreUpdate runs first)
	// DeltaSeconds follows the owner's CustomTimeDilation: hit-stop freezes both clips
	if (!bCurFresh)
	{
		Advance(Cur, DeltaSeconds);
	}
	bCurFresh = false;
	if (BlendLeft > 0.f)
	{
		if (!bPrevIsSnapshot)
		{
			Advance(Prev, DeltaSeconds);   // the old clip keeps moving while it fades (a frozen one reads as a hitch)
		}
		BlendLeft = FMath::Max(0.f, BlendLeft - DeltaSeconds);
		if (BlendLeft <= 0.f)
		{
			Prev = FNyabloAnimSlot();
			bPrevIsSnapshot = false;
		}
	}
}

void FNyabloAnimProxy::PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
	const UNyabloAnimInstance* Instance = CastChecked<UNyabloAnimInstance>(InAnimInstance);
	Cur = Instance->Cur;
	Prev = Instance->Prev;
	bPrevIsSnapshot = Instance->bPrevIsSnapshot;
	SnapshotRequest = Instance->SnapshotRequest;
	const float U = Instance->BlendTotal > 0.f ? 1.f - Instance->BlendLeft / Instance->BlendTotal : 1.f;
	CurWeight = Prev.Anim ? FMath::SmoothStep(0.f, 1.f, U) : 1.f;
}

static void ExtractSlot(const FNyabloAnimSlot& Slot, FPoseContext& Out)
{
	FAnimationPoseData Data(Out);
	Slot.Anim->GetAnimationPose(Data, FAnimExtractContext(static_cast<double>(Slot.Time), false, {}, Slot.bLoop));
}

static void AddRootOffset(FPoseContext& Out, const FVector& Offset)
{
	if (!Offset.IsNearlyZero() && Out.Pose.GetNumBones() > 0)
	{
		Out.Pose[FCompactPoseBoneIndex(0)].AddToTranslation(Offset);
	}
}

bool FNyabloAnimProxy::Evaluate(FPoseContext& Output)
{
	if (!Cur.Anim)
	{
		Output.ResetToRefPose();
		return true;
	}
	const int32 NumBones = Output.Pose.GetNumBones();
	if (SnapshotTaken != SnapshotRequest)
	{
		Snapshot = LastOutput;                // the pose drawn last frame
		SnapshotTaken = SnapshotRequest;
	}
	ExtractSlot(Cur, Output);
	AddRootOffset(Output, Cur.RootOffset);
	if (Prev.Anim && CurWeight < 1.f)
	{
		FPoseContext PrevPose(Output);
		bool bHavePrev = true;
		if (bPrevIsSnapshot)
		{
			bHavePrev = Snapshot.Num() == NumBones;
			for (int32 i = 0; bHavePrev && i < NumBones; ++i)
			{
				PrevPose.Pose[FCompactPoseBoneIndex(i)] = Snapshot[i];
			}
		}
		else
		{
			ExtractSlot(Prev, PrevPose);
		}
		if (bHavePrev)
		{
			AddRootOffset(PrevPose, Prev.RootOffset);
			FAnimationPoseData OutData(Output);
			const FAnimationPoseData PrevData(PrevPose);
			FAnimationRuntime::BlendTwoPosesTogetherInPlace(OutData, PrevData, CurWeight);
		}
	}
	LastOutput.SetNum(NumBones, EAllowShrinking::No);
	for (int32 i = 0; i < NumBones; ++i)
	{
		LastOutput[i] = Output.Pose[FCompactPoseBoneIndex(i)];
	}
	return true;
}
