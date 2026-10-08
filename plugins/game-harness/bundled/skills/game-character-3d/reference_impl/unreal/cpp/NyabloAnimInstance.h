#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "NyabloAnimInstance.generated.h"

class UAnimSequence;

/** One playing clip: time advances by rate; RootOffset (component space) shifts the whole pose (lunge catch-up). */
struct FNyabloAnimSlot
{
	UAnimSequence* Anim = nullptr;
	float Time = 0.f;
	float Rate = 1.f;
	bool bLoop = false;
	/** > 0: never plays past this (s). An attack clip fading out must not run into the next combo window, whose
	 *  hip travel restarts at 0 (the body was pulled back ~1 m). */
	float MaxTime = 0.f;
	FVector RootOffset = FVector::ZeroVector;
};

struct FNyabloAnimProxy : public FAnimInstanceProxy
{
	FNyabloAnimProxy() = default;
	explicit FNyabloAnimProxy(UAnimInstance* InInstance) : FAnimInstanceProxy(InInstance) {}

	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual bool Evaluate(FPoseContext& Output) override;

	FNyabloAnimSlot Cur;
	FNyabloAnimSlot Prev;
	bool bPrevIsSnapshot = false;
	int32 SnapshotRequest = 0;
	float CurWeight = 1.f;

	/** What was drawn last frame (local bone transforms): the frozen source when a fade is interrupted. */
	TArray<FTransform> LastOutput;
	TArray<FTransform> Snapshot;
	int32 SnapshotTaken = 0;
};

/**
 * Crossfading clip player (4-28). The single-node player cut every clip change in one frame: swing end -> idle,
 * run -> swing and combo -> combo popped the pose by 14-35 % of body height. Play() keeps the old clip running and
 * fades to the new one over BlendTime (smoothstep). A Play() that interrupts a fade freezes what is on screen
 * (last drawn pose) and fades from that, so no half-visible pose is dropped. No anim graph asset: the proxy
 * evaluates the sequences itself.
 */
UCLASS(Transient, NotBlueprintable)
class NYABLO_API UNyabloAnimInstance : public UAnimInstance
{
	GENERATED_BODY()

public:
	void Play(UAnimSequence* Anim, bool bLoop, float BlendTime, float StartTime = 0.f, float Rate = 1.f, float MaxTime = 0.f);
	float GetPosition() const { return Cur.Time; }
	void SetPosition(float Time) { Cur.Time = Time; }
	float GetRate() const { return Cur.Rate; }
	void SetRate(float Rate) { Cur.Rate = Rate; }
	UAnimSequence* GetCurrentAnim() const { return Cur.Anim; }
	/** The capsule moved by -Delta under the body: shift every playing clip so nothing jumps (component space). */
	void ShiftRoots(const FVector& Delta);
	/** Increments on every Play (frames where the clip changed, for the pose-jump check). */
	int32 GetPlayCount() const { return PlayCount; }

	FNyabloAnimSlot Cur;
	FNyabloAnimSlot Prev;
	bool bPrevIsSnapshot = false;
	int32 SnapshotRequest = 0;
	float BlendTotal = 0.f;
	float BlendLeft = 0.f;

protected:
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override { return new FNyabloAnimProxy(this); }
	virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* InProxy) override { delete InProxy; }

private:
	static void Advance(FNyabloAnimSlot& Slot, float DeltaSeconds);
	bool bCurFresh = false;
	int32 PlayCount = 0;
	/** Capsule moves since the last pose was drawn: a snapshot taken now must carry them. */
	FVector PendingShift = FVector::ZeroVector;
};
